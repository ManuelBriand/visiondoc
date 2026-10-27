"""Benchmark de la V0 (spec A6, étape 5) : rapport Markdown et JSON.

    uv run --project apps/inference --extra ocr python benchmarks/run.py

Mesure, par type de pièce :
- précision par champ en conditions nominales : exact, faux signalé, faux non signalé, absent ;
- robustesse à des prises de vue dégradées : flou, inclinaison, éclairage, compression,
  résolution ;
- temps total et par étape ;
- spécimens officiels annotés de `benchmarks/specimens/` s'il y en a (voir le README).

Un champ faux est signalé si sa confiance est < 0,9 ou s'il porte un avertissement. Le
rapport ne contient aucune valeur extraite : seulement des comptes et des temps.
"""

import argparse
import json
import os
import platform
import random
import statistics
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from inference.errors import ExtractionError
from inference.ocr.mrz_reader import PaddleLineRecognizer
from inference.ocr.text_engine import PaddleTextEngine
from inference.pipeline.extract import extract
from inference.pipeline.models import Extraction
from inference.synth.documents import Capture, DocumentKind, Fonts, Specimen, make_specimen
from inference.synth.fonts import ocrb_font_path, text_font_path
from inference.text import fold, normalize_name
from inference.timing import collect

KINDS: tuple[DocumentKind, ...] = ("fr_id_card_2021", "fr_id_card_legacy", "fr_passport")
KIND_LABELS = {
    "fr_id_card_2021": "Nouvelle CNI",
    "fr_id_card_legacy": "Ancienne CNI",
    "fr_passport": "Passeport",
}
OUTCOMES = ("exact", "signalé", "NON SIGNALÉ", "absent")
STAGES = ("file", "document", "mrz_locate", "mrz_ocr", "mrz_parse", "visual_ocr", "fusion")
TODAY = date(2026, 10, 22)

DEGRADED: tuple[tuple[str, Capture], ...] = (
    ("flou sigma 1,0", Capture(blur_sigma=1.0)),
    ("flou sigma 1,5", Capture(blur_sigma=1.5)),
    ("flou sigma 2,0", Capture(blur_sigma=2.0)),
    ("flou sigma 2,5", Capture(blur_sigma=2.5)),
    ("flou sigma 3,0", Capture(blur_sigma=3.0)),
    ("inclinaison 20°", Capture(angle=20)),
    ("inclinaison 30°", Capture(angle=30)),
    ("inclinaison 45°", Capture(angle=45)),
    ("sombre x 0,5", Capture(brightness=0.5)),
    ("sombre x 0,3", Capture(brightness=0.3)),
    ("surexposé x 1,6", Capture(brightness=1.6)),
    ("JPEG q 40", Capture(jpeg_quality=40)),
    ("JPEG q 20", Capture(jpeg_quality=20)),
    ("JPEG q 10", Capture(jpeg_quality=10)),
    ("photo 1 200 px", Capture(width=1200)),
    ("photo 900 px", Capture(width=900)),
    ("photo 700 px", Capture(width=700)),
)


@dataclass
class Case:
    """Une extraction : identifiants, résultat par champ et temps. Aucune valeur."""

    source: str  # "synthétique" ou "officiel"
    condition: str
    kind: str
    outcome: str  # "accepté" ou code d'erreur
    fields: dict[str, str] = field(default_factory=dict)
    seconds: float = 0.0
    stages: dict[str, float] = field(default_factory=dict)


def _add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def expected(specimen: Specimen) -> dict[str, Any]:
    who = specimen.identity
    truth: dict[str, Any] = {
        "last_name": normalize_name(who.last_name),
        "first_names": [normalize_name(name) for name in who.first_names],
        "birth_date": who.birth_date.isoformat(),
        "sex": who.sex,
        "document_number": who.document_number,
        "issue_date": specimen.issue_date.isoformat(),
        "birth_place": fold(specimen.birth_place),
    }
    expiry = specimen.printed_expiry
    if specimen.kind == "fr_id_card_legacy":
        adult = _add_years(who.birth_date, 18) <= specimen.issue_date
        if adult and date(2004, 1, 2) <= specimen.issue_date <= date(2013, 12, 31):
            expiry = _add_years(expiry, 5)
    truth["expiry_date"] = expiry.isoformat()
    if specimen.kind == "fr_passport":
        truth["nationality"] = "FRA"
    return truth


def judge(result: Extraction, truth: dict[str, Any]) -> dict[str, str]:
    verdicts: dict[str, str] = {}
    for name, value in truth.items():
        found = result.fields.get(name)
        if found is None:
            verdicts[name] = "absent"
        elif found.value == value:
            verdicts[name] = "exact"
        elif found.confidence < 0.9 or any(w.field == name for w in result.warnings):
            verdicts[name] = "signalé"
        else:
            verdicts[name] = "NON SIGNALÉ"
    return verdicts


class Runner:
    def __init__(self, recognizer: PaddleLineRecognizer, engine: PaddleTextEngine) -> None:
        self.recognizer, self.engine = recognizer, engine

    def run(
        self, source: str, condition: str, kind: str, front: bytes, back: bytes | None,
        truth: dict[str, Any],
    ) -> Case:  # fmt: skip
        case = Case(source=source, condition=condition, kind=kind, outcome="accepté")
        started = time.perf_counter()
        with collect() as timings:
            try:
                result = extract(front, back, self.recognizer, self.engine, today=TODAY)
            except ExtractionError as exc:
                case.outcome = exc.code
            else:
                case.fields = judge(result, truth)
        case.seconds = time.perf_counter() - started
        case.stages = dict(timings)
        return case


def synthetic_cases(
    runner: Runner, fonts: Fonts, seed: int, nominal: int, degraded: int
) -> list[Case]:
    cases: list[Case] = []
    plan = [("nominal", Capture(), nominal), *((name, c, degraded) for name, c in DEGRADED)]
    for index, (condition, capture, count) in enumerate(plan):
        rng = random.Random(seed + index)  # noqa: S311 - spécimens reproductibles par graine
        for kind in KINDS:
            for n in range(count):
                shot = capture
                if condition == "nominal" and n % 4 == 3:
                    shot = Capture(upside_down=True)
                specimen = make_specimen(kind, rng, fonts, shot)
                front, back = specimen.image, specimen.other_image
                if kind == "fr_id_card_2021" and n % 2 == 0:
                    front, back = back or b"", front  # recto d'abord, comme un vrai envoi
                cases.append(
                    runner.run("synthétique", condition, kind, front, back, expected(specimen))
                )
            print(f"{condition:<18} {kind:<18} {count} documents", flush=True)
    return cases


def official_cases(runner: Runner, root: Path) -> list[Case]:
    """`specimens/<type>/<nom>.json` : {"front": …, "back": …, "expected": {champ: valeur}}."""
    cases: list[Case] = []
    for annotation in sorted(root.glob("*/*.json")):
        spec = json.loads(annotation.read_text())
        front = (annotation.parent / spec["front"]).read_bytes()
        back = (annotation.parent / spec["back"]).read_bytes() if spec.get("back") else None
        kind = annotation.parent.name
        cases.append(runner.run("officiel", annotation.stem, kind, front, back, spec["expected"]))
    return cases


def _pct(part: int, whole: int) -> str:
    return "—" if whole == 0 else f"{100 * part / whole:.1f} %"


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))] if ordered else 0.0


def _field_table(cases: list[Case]) -> list[str]:
    counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for case in cases:
        for name, verdict in case.fields.items():
            counts[(case.kind, name)][verdict] += 1
    lines = [
        "| Type | Champ | Exacts | Faux signalés | **Faux non signalés** | Absents |",
        "|---|---|---|---|---|---|",
    ]
    for (kind, name), c in sorted(counts.items()):
        total = sum(c.values())
        lines.append(
            f"| {KIND_LABELS.get(kind, kind)} | {name} | {c['exact']} / {total} "
            f"({_pct(c['exact'], total)}) | {c['signalé']} | **{c['NON SIGNALÉ']}** "
            f"| {c['absent']} |"
        )
    return lines


def _document_table(cases: list[Case]) -> list[str]:
    lines = [
        "| Type | Documents | Acceptés | Tous champs exacts | Refus (code : nombre) "
        "| Temps médian | p95 |",
        "|---|---|---|---|---|---|---|",
    ]
    for kind in sorted({c.kind for c in cases}):
        mine = [c for c in cases if c.kind == kind]
        accepted = [c for c in mine if c.outcome == "accepté"]
        perfect = [c for c in accepted if all(v == "exact" for v in c.fields.values())]
        refusals = Counter(c.outcome for c in mine if c.outcome != "accepté")
        times = [c.seconds for c in accepted]
        lines.append(
            f"| {KIND_LABELS.get(kind, kind)} | {len(mine)} | {_pct(len(accepted), len(mine))} | "
            f"{_pct(len(perfect), len(mine))} | "
            f"{', '.join(f'{k} : {v}' for k, v in sorted(refusals.items())) or '—'} | "
            f"{statistics.median(times) if times else 0:.2f} s | {_quantile(times, 0.95):.2f} s |"
        )
    return lines


def _robustness_table(cases: list[Case]) -> list[str]:
    lines = [
        "| Condition | Acceptés | Refus | Champs exacts (acceptés) | **Faux non signalés** |",
        "|---|---|---|---|---|",
    ]
    for condition in ["nominal", *(name for name, _ in DEGRADED)]:
        mine = [c for c in cases if c.condition == condition]
        if not mine:
            continue
        accepted = [c for c in mine if c.outcome == "accepté"]
        verdicts = Counter(v for c in accepted for v in c.fields.values())
        refusals = Counter(c.outcome for c in mine if c.outcome != "accepté")
        lines.append(
            f"| {condition} | {_pct(len(accepted), len(mine))} | "
            f"{', '.join(f'{k} : {v}' for k, v in sorted(refusals.items())) or '—'} | "
            f"{_pct(verdicts['exact'], sum(verdicts.values()))} | **{verdicts['NON SIGNALÉ']}** |"
        )
    return lines


def _stage_table(cases: list[Case]) -> list[str]:
    accepted = [c for c in cases if c.outcome == "accepté"]
    lines = ["| Étape | " + " | ".join(KIND_LABELS[k] for k in KINDS) + " |"]
    lines.append("|---" * (len(KINDS) + 1) + "|")
    for stage in STAGES:
        row = []
        for kind in KINDS:
            values = [c.stages.get(stage, 0.0) for c in accepted if c.kind == kind]
            row.append(f"{1000 * statistics.median(values):.0f} ms" if values else "—")
        lines.append(f"| `{stage}` | " + " | ".join(row) + " |")
    return lines


def _environment(args: argparse.Namespace) -> dict[str, Any]:
    try:
        command = ["git", "rev-parse", "--short", "HEAD"]
        done = subprocess.run(command, capture_output=True, text=True, check=True)  # noqa: S603
        commit = done.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = os.environ.get("GITHUB_SHA", "inconnu")[:7]
    return {
        "date": datetime.now().isoformat(timespec="seconds"),
        "commit": commit,
        "machine": f"{platform.system()} {platform.machine()}, {os.cpu_count()} processeurs",
        "python": platform.python_version(),
        "paddlepaddle": version("paddlepaddle"),
        "paddleocr": version("paddleocr"),
        "det_max_side": args.det_max_side,
        "cpu_threads": args.cpu_threads,
        "seed": args.seed,
        "nominal_per_kind": args.nominal,
        "degraded_per_kind": args.degraded,
    }


def write_report(cases: list[Case], env: dict[str, Any], out: Path, label: str) -> Path:
    synthetic = [c for c in cases if c.source == "synthétique"]
    nominal = [c for c in synthetic if c.condition == "nominal"]
    official = [c for c in cases if c.source == "officiel"]
    verdicts = Counter(v for c in nominal for v in c.fields.values())
    lines = [
        f"# Benchmark V0 — {label}",
        "",
        "| Paramètre | Valeur |",
        "|---|---|",
        *(f"| {key} | {value} |" for key, value in env.items()),
        "",
        "## Synthèse (conditions nominales)",
        "",
        f"- Champs évalués : {sum(verdicts.values())} ; exacts : "
        f"{_pct(verdicts['exact'], sum(verdicts.values()))} ; "
        f"**faux non signalés : {verdicts['NON SIGNALÉ']}**.",
        "- Un champ faux est signalé si sa confiance est < 0,9 ou s'il porte un avertissement.",
        "- Spécimens synthétiques : à confirmer sur des spécimens officiels.",
        "",
        "### Par document",
        "",
        *_document_table(nominal),
        "",
        "### Par champ",
        "",
        *_field_table(nominal),
        "",
        "## Robustesse (tous types confondus)",
        "",
        *_robustness_table(synthetic),
        "",
        "## Temps médian par étape (conditions nominales, documents acceptés)",
        "",
        *_stage_table(nominal),
        "",
        "## Spécimens officiels",
        "",
    ]
    if official:
        lines += ["### Par document", "", *_document_table(official), "", "### Par champ", ""]
        lines += _field_table(official)
    else:
        lines.append("Aucun spécimen officiel annoté dans `benchmarks/specimens/`.")
    stem = f"{date.today().isoformat()}-{label}"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{stem}.md").write_text("\n".join(lines) + "\n")
    (out / f"{stem}.json").write_text(
        json.dumps({"environment": env, "cases": [asdict(c) for c in cases]}, ensure_ascii=False)
    )
    return out / f"{stem}.md"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nominal", type=int, default=100, help="documents par type")
    parser.add_argument("--degraded", type=int, default=15, help="par type et par condition")
    parser.add_argument("--seed", type=int, default=20261101)
    parser.add_argument("--det-max-side", type=int, default=None)
    parser.add_argument("--cpu-threads", type=int, default=None)
    parser.add_argument("--label", default="local")
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "reports")
    parser.add_argument("--specimens", type=Path, default=Path(__file__).parent / "specimens")
    args = parser.parse_args()

    runner = Runner(
        PaddleLineRecognizer(cpu_threads=args.cpu_threads),
        PaddleTextEngine(det_max_side=args.det_max_side, cpu_threads=args.cpu_threads),
    )
    fonts = Fonts(mrz=ocrb_font_path(), text=text_font_path())
    cases = synthetic_cases(runner, fonts, args.seed, args.nominal, args.degraded)
    cases += official_cases(runner, args.specimens)
    report = write_report(cases, _environment(args), args.out, args.label)
    print(f"Rapport : {report}")


if __name__ == "__main__":
    main()

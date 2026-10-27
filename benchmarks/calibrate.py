"""Calibrage des seuils : netteté minimale, et réglages de performance de l'OCR.

    uv run --project apps/inference --extra ocr python benchmarks/calibrate.py quality
    uv run --project apps/inference --extra ocr python benchmarks/calibrate.py speed

`quality`, `bright`, `dark` : photos de plus en plus floues, surexposées ou sombres ; pour
chacune, la mesure de qualité et le résultat de l'extraction avec les contrôles désactivés.
Un seuil doit refuser les photos qu'on ne sait pas lire, et seulement elles.

`speed` : mêmes documents, plusieurs réglages de PaddleOCR (threads, taille de l'image de
détection) ; temps et précision de chacun.
"""

import argparse
import random
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import run

from inference.errors import ExtractionError
from inference.ocr.mrz_reader import PaddleLineRecognizer
from inference.ocr.text_engine import PaddleTextEngine
from inference.pipeline.extract import extract
from inference.synth.documents import Capture, Fonts, make_specimen
from inference.synth.fonts import ocrb_font_path, text_font_path
from inference.vision import quality
from inference.vision.document import crop_document
from inference.vision.file_check import load_image

# Étude → (libellé, mesure de qualité observée, niveaux de prise de vue)
STUDIES: dict[str, tuple[str, str, tuple[tuple[str, Capture], ...]]] = {
    "quality": (
        "Flou sigma",
        "sharpness",
        tuple(
            (str(s), Capture(blur_sigma=s)) for s in (0.0, 0.5, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)
        ),
    ),
    "bright": (
        "Éclairage",
        "saturated_ratio",
        tuple((f"x {b}", Capture(brightness=b)) for b in (1.0, 1.2, 1.4, 1.6, 1.8, 2.0)),
    ),
    "dark": (
        "Éclairage",
        "brightness",
        tuple((f"x {b}", Capture(brightness=b)) for b in (0.5, 0.4, 0.3, 0.25, 0.2, 0.15)),
    ),
}


def calibrate_quality(study: str, per_level: int, seed: int) -> None:
    label, metric, levels = STUDIES[study]
    fonts = Fonts(mrz=ocrb_font_path(), text=text_font_path())
    recognizer, engine = PaddleLineRecognizer(), PaddleTextEngine()
    # Contrôles désactivés pour l'étude : on veut savoir ce qu'on aurait lu.
    quality.MIN_SHARPNESS = 0.0
    quality.MIN_BRIGHTNESS = 0.0
    print(
        f"| {label} | {metric} médiane (min - max) | Lus sans erreur | Faux signalés "
        "| **Faux non signalés** | Autres refus |"
    )
    print("|---|---|---|---|---|---|")
    for index, (level, capture) in enumerate(levels):
        rng = random.Random(seed + index)  # noqa: S311 - spécimens reproductibles par graine
        sharpness: list[float] = []
        outcomes: Counter[str] = Counter()
        for n in range(per_level):
            kind = run.KINDS[n % len(run.KINDS)]
            specimen = make_specimen(kind, rng, fonts, capture)
            report = quality.measure(crop_document(load_image(specimen.image)).image)
            sharpness.append(float(getattr(report, metric)))
            front, back = specimen.image, specimen.other_image
            try:
                result = extract(front, back, recognizer, engine, today=run.TODAY)
            except ExtractionError as exc:
                outcomes[exc.code] += 1
                continue
            verdicts = Counter(run.judge(result, run.expected(specimen)).values())
            if verdicts["NON SIGNALÉ"]:
                outcomes["non signalé"] += 1
            elif verdicts["signalé"] or verdicts["absent"]:
                outcomes["signalé"] += 1
            else:
                outcomes["exact"] += 1
        others = per_level - outcomes["exact"] - outcomes["signalé"] - outcomes["non signalé"]
        print(
            f"| {level} | {statistics.median(sharpness):.3g} ({min(sharpness):.3g} - "
            f"{max(sharpness):.3g}) | {outcomes['exact']} / {per_level} | {outcomes['signalé']} "
            f"| **{outcomes['non signalé']}** | {others} |",
            flush=True,
        )


def calibrate_speed(per_kind: int, seed: int, configs: list[tuple[int | None, int | None]]) -> None:
    fonts = Fonts(mrz=ocrb_font_path(), text=text_font_path())
    rng = random.Random(seed)  # noqa: S311 - spécimens reproductibles par graine
    specimens = [make_specimen(k, rng, fonts) for k in run.KINDS for _ in range(per_kind)]
    print(
        "| Détection (côté max) | Threads | Temps médian | p95 | Champs exacts "
        "| **Faux non signalés** |"
    )
    print("|---|---|---|---|---|---|")
    for det_max_side, threads in configs:
        recognizer = PaddleLineRecognizer(cpu_threads=threads)
        engine = PaddleTextEngine(det_max_side=det_max_side, cpu_threads=threads)
        extract(specimens[0].image, specimens[0].other_image, recognizer, engine)  # chauffe
        times: list[float] = []
        verdicts: Counter[str] = Counter()
        for specimen in specimens:
            started = time.perf_counter()
            try:
                result = extract(
                    specimen.image, specimen.other_image, recognizer, engine, today=run.TODAY
                )
            except ExtractionError:
                verdicts["refus"] += 1
                continue
            times.append(time.perf_counter() - started)
            verdicts.update(run.judge(result, run.expected(specimen)).values())
        total = sum(v for k, v in verdicts.items() if k != "refus")
        print(
            f"| {det_max_side or 'pleine résolution'} | {threads or 'défaut (10)'} "
            f"| {statistics.median(times):.2f} s | {run._quantile(times, 0.95):.2f} s "
            f"| {run._pct(verdicts['exact'], total)} | **{verdicts['NON SIGNALÉ']}** |",
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("study", choices=(*STUDIES, "speed"))
    parser.add_argument("--count", type=int, default=24)
    parser.add_argument("--seed", type=int, default=20261102)
    parser.add_argument(
        "--threads", type=int, nargs="*", default=[2, 4], help="nombres de threads à comparer"
    )
    args = parser.parse_args()
    if args.study in STUDIES:
        calibrate_quality(args.study, args.count, args.seed)
    else:
        configs: list[tuple[int | None, int | None]] = [(None, None)]
        configs += [(None, t) for t in args.threads]
        configs += [(side, args.threads[-1]) for side in (960, 736, 640)]
        calibrate_speed(args.count, args.seed, configs)


if __name__ == "__main__":
    main()

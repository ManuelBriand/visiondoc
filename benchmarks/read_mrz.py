"""Mesure de l'étape 2 : lecture de la MRZ sur des spécimens synthétiques générés à la volée.

    uv run --project apps/inference --extra ocr python benchmarks/read_mrz.py --per-kind 50

Rien n'est écrit sur disque : les images restent en mémoire.
"""

import argparse
import random
import time
from collections import Counter
from datetime import date

from inference.errors import ExtractionError
from inference.ocr.mrz_reader import PaddleLineRecognizer
from inference.pipeline.read_mrz import read_mrz
from inference.synth.documents import Capture, DocumentKind, Fonts, make_specimen
from inference.synth.fonts import ocrb_font_path, text_font_path
from inference.text import normalize_name

KINDS: tuple[DocumentKind, ...] = ("fr_id_card_2021", "fr_id_card_legacy", "fr_passport")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-kind", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20261022)
    parser.add_argument("--blur-sigma", type=float, default=3.5)
    args = parser.parse_args()

    fonts = Fonts(mrz=ocrb_font_path(), text=text_font_path())
    recognizer = PaddleLineRecognizer()
    rng = random.Random(args.seed)  # noqa: S311 - spécimens reproductibles par graine
    today = date(2026, 10, 22)
    outcomes: Counter[tuple[str, str, str]] = Counter()
    durations: list[float] = []

    for kind in KINDS:
        for index in range(args.per_kind):
            for label, blur in (("net", 0.0), ("flou", args.blur_sigma)):
                specimen = make_specimen(
                    kind, rng, fonts, Capture(blur_sigma=blur, upside_down=index % 4 == 3)
                )
                start = time.perf_counter()
                try:
                    mrz = read_mrz(specimen.image, recognizer, today=today).mrz
                except ExtractionError as exc:
                    outcomes[(kind, label, exc.code)] += 1
                    continue
                finally:
                    durations.append(time.perf_counter() - start)
                if not mrz.checksums_valid:
                    outcome = "clés invalides (signalé)"
                elif mrz.document_number == specimen.identity.document_number and (
                    mrz.last_name == normalize_name(specimen.identity.last_name)
                    and mrz.birth_date == specimen.identity.birth_date
                ):
                    outcome = "lu"
                else:
                    outcome = "ERREUR SILENCIEUSE"
                outcomes[(kind, label, outcome)] += 1

    print(f"{'type':<20}{'image':<7}{'résultat':<28}{'nombre':>7}")
    for (doc_kind, label, outcome), count in sorted(outcomes.items()):
        print(f"{doc_kind:<20}{label:<7}{outcome:<28}{count:>7}")
    durations.sort()
    median = durations[len(durations) // 2]
    p95 = durations[int(len(durations) * 0.95)]
    print(f"\ntemps par image : médiane {median * 1000:.0f} ms, p95 {p95 * 1000:.0f} ms")


if __name__ == "__main__":
    main()

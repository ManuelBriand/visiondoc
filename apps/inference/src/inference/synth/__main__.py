"""Écrit un spécimen synthétique sur disque, pour des essais manuels ou un test de fumée.

    python -m inference.synth --kind fr_passport --seed 1 --out /tmp/passeport.jpg

Spécimen entièrement synthétique : aucune donnée réelle.
"""

import argparse
import random
from pathlib import Path
from typing import get_args

from inference.synth.documents import DocumentKind, Fonts, make_specimen
from inference.synth.fonts import ocrb_font_path, text_font_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=get_args(DocumentKind), default="fr_passport")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    fonts = Fonts(mrz=ocrb_font_path(), text=text_font_path())
    specimen = make_specimen(args.kind, random.Random(args.seed), fonts)  # noqa: S311
    args.out.write_bytes(specimen.image)
    if specimen.other_image is not None:
        other = args.out.with_stem(args.out.stem + "_autre_face")
        other.write_bytes(specimen.other_image)
    print(f"Spécimen écrit : {args.out}")

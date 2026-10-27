"""Contrôle du fichier reçu et décodage en mémoire (spec A4, étape 1).

- vrai type vérifié par signature binaire, jamais par extension ;
- taille plafonnée ;
- nombre de pixels vérifié sur l'en-tête, avant décodage (images piégées) ;
- PDF d'une page rendu dans un processus séparé, tué au-delà d'un délai ;
- rien n'est écrit sur disque.
"""

import io
import multiprocessing as mp
from multiprocessing.connection import Connection
from typing import Literal

import numpy as np
from cv2.typing import MatLike
from PIL import Image, ImageOps

from inference.errors import ExtractionError

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 40_000_000
PDF_RENDER_DPI = 300
PDF_TIMEOUT_SECONDS = 15.0

FileKind = Literal["jpeg", "png", "pdf"]

_SIGNATURES: tuple[tuple[bytes, FileKind], ...] = (
    (b"\xff\xd8\xff", "jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"%PDF-", "pdf"),
)
_PIL_FORMATS: dict[FileKind, str] = {"jpeg": "JPEG", "png": "PNG"}


def _invalid() -> ExtractionError:
    return ExtractionError("invalid_format", "Format non accepté ou fichier corrompu.")


def sniff(data: bytes) -> FileKind:
    for signature, kind in _SIGNATURES:
        if data.startswith(signature):
            return kind
    raise _invalid()


def load_image(data: bytes) -> MatLike:
    """Contrôle le fichier puis renvoie l'image en BGR, orientation EXIF appliquée."""
    if len(data) > MAX_FILE_BYTES:
        raise ExtractionError("file_too_large", "Le fichier dépasse 10 Mo.")
    kind = sniff(data)
    if kind == "pdf":
        return render_pdf(data)
    return _decode_raster(data, kind)


def _decode_raster(data: bytes, kind: FileKind) -> MatLike:
    try:
        with Image.open(io.BytesIO(data), formats=[_PIL_FORMATS[kind]]) as img:
            width, height = img.size
            if width * height > MAX_PIXELS:
                raise _invalid()
            img.load()
            upright = ImageOps.exif_transpose(img).convert("RGB")
    except ExtractionError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise _invalid() from exc
    rgb = np.asarray(upright)
    return np.ascontiguousarray(rgb[:, :, ::-1])


def _render_pdf_worker(data: bytes, conn: Connection) -> None:
    """Exécuté dans un processus dédié : un PDF malveillant ne touche pas le service."""
    # Import tardif : chargé uniquement dans le processus isolé.
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(data)
        if len(pdf) != 1:
            conn.send(None)
            return
        page = pdf[0]
        width_pt, height_pt = page.get_size()
        scale = PDF_RENDER_DPI / 72
        pixels = width_pt * height_pt * scale * scale
        if pixels > MAX_PIXELS:
            scale *= (MAX_PIXELS / pixels) ** 0.5
        # Rendu sans formulaires ni annotations : aucun contenu actif n'est exécuté.
        bitmap = page.render(scale=scale, may_draw_forms=False, draw_annots=False)
        conn.send(np.ascontiguousarray(bitmap.to_numpy()[:, :, :3]))
    except Exception:  # toute erreur du parseur PDF vaut fichier invalide
        conn.send(None)
    finally:
        conn.close()


def render_pdf(data: bytes) -> MatLike:
    ctx = mp.get_context("spawn")
    receiver, sender = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_render_pdf_worker, args=(data, sender), daemon=True)
    process.start()
    sender.close()
    try:
        if not receiver.poll(PDF_TIMEOUT_SECONDS):
            raise _invalid()
        result = receiver.recv()
    except EOFError as exc:
        raise _invalid() from exc
    finally:
        receiver.close()
        process.join(timeout=1)
        if process.is_alive():
            process.kill()
            process.join()
    if not isinstance(result, np.ndarray):
        raise _invalid()
    return result

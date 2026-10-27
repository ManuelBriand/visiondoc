"""Point d'entrée du serveur : `uvicorn inference.api.main:app`."""

from inference.api import logs
from inference.api.app import create_app
from inference.api.settings import Settings
from inference.api.warmup import warm
from inference.ocr.mrz_reader import PaddleLineRecognizer
from inference.ocr.text_engine import PaddleTextEngine

MODELS = {
    "mrz_recognition": PaddleLineRecognizer.MODEL_NAME,
    "text_detection": PaddleTextEngine.DETECTION_MODEL,
    "text_recognition": PaddleTextEngine.RECOGNITION_MODEL,
}

logs.configure()
settings = Settings()
recognizer = PaddleLineRecognizer(cpu_threads=settings.cpu_threads)
engine = PaddleTextEngine(det_max_side=settings.det_max_side, cpu_threads=settings.cpu_threads)
warm(recognizer, engine)  # avant d'accepter des requêtes : /health ne répond qu'une fois prêt
app = create_app(settings, recognizer, engine, MODELS)

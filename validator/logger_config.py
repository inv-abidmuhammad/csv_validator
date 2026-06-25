import logging
from pathlib import Path

def setup_logger():
    Path("logs").mkdir(exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    file_handler = logging.FileHandler("logs/validator.log")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)
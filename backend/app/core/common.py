import json
import os
from pathlib import Path

from dotenv import load_dotenv


CORE_DIR = Path(__file__).resolve().parent
APP_DIR = CORE_DIR.parent
PROJECT_ROOT = APP_DIR.parent
OUTPUT_DIR = PROJECT_ROOT / "outputs"
SAMPLE_PDF_PATH = PROJECT_ROOT / "sample.pdf"
ENV_PATH = PROJECT_ROOT / ".env"


def load_project_env() -> None:
    load_dotenv(ENV_PATH)


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name}를 .env에서 읽지 못했습니다.")
    return value


def ensure_output_dir() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def save_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def write_text(path: Path, content: str) -> None:
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)


def build_result(
    status: str,
    data: dict | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    debug: dict | None = None,
) -> dict:
    return {
        "status": status,
        "data": data,
        "error_code": error_code,
        "error_message": error_message,
        "debug": debug or {},
    }

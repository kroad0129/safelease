import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO

from app.services.contract_verifier import verify_contract_pdf
from app.services.verification_persistence import persist_verification_outputs


def verify_contract_path(pdf_path: str) -> dict:
    result = verify_contract_pdf(pdf_path)
    result["output_paths"] = persist_verification_outputs(result, source_pdf_path=pdf_path)
    return result


def verify_contract_upload_stream(filename: str, file_obj: BinaryIO) -> dict:
    suffix = Path(filename or "upload.pdf").suffix or ".pdf"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
        shutil.copyfileobj(file_obj, temp_file)
        temp_path = Path(temp_file.name)

    try:
        return verify_contract_path(str(temp_path))
    finally:
        temp_path.unlink(missing_ok=True)

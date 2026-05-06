import json
import sys
from pathlib import Path

from app.core.common import SAMPLE_PDF_PATH
from app.services.contract_service import verify_contract_path


def resolve_pdf_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return SAMPLE_PDF_PATH.resolve()


def main() -> None:
    pdf_path = resolve_pdf_path()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")

    result = verify_contract_path(str(pdf_path))
    output_paths = result.get("output_paths", {})
    rag_status = (result.get("rag_analysis") or {}).get("status")
    verification_summary = result["verification"]["analysis"]["summary"]

    report = {
        "input_pdf": str(pdf_path),
        "rule_review_level": verification_summary.get("review_level"),
        "rule_finding_count": verification_summary.get("finding_count"),
        "rag_status": rag_status,
        "run_dir": output_paths.get("run_dir"),
        "combined_result_json": output_paths.get("combined_output_path"),
        "highlighted_pdf": output_paths.get("highlighted_pdf_path"),
        "rag_analysis_json": output_paths.get("rag_analysis_path"),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

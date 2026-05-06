from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.core.common import OUTPUT_DIR, ensure_output_dir, save_json
from app.core.progress import log_step
from app.services.pdf_highlight_service import generate_finding_highlight_artifacts
from app.services.privacy_masking import build_public_result, mask_sensitive_data
from app.services.rag_analysis_service import analyze_contract_with_rag


def build_output_run_dir() -> Path:
    ensure_output_dir()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
    run_dir = OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _build_base_output_paths(run_dir: Path) -> dict:
    extracted_output_path = run_dir / "extracted_contract.json"
    verification_output_path = run_dir / "verification_result.json"
    analysis_output_path = run_dir / "analysis_result.json"
    combined_output_path = run_dir / "combined_result.json"

    return {
        "run_dir": str(run_dir),
        "extracted_output_path": str(extracted_output_path),
        "verification_output_path": str(verification_output_path),
        "analysis_output_path": str(analysis_output_path),
        "combined_output_path": str(combined_output_path),
    }


def _save_base_outputs(result: dict, output_paths: dict) -> None:
    log_step(14, "추출/검증/분석 JSON 저장 중")
    save_json(Path(output_paths["extracted_output_path"]), mask_sensitive_data(result["extracted"]))
    save_json(Path(output_paths["verification_output_path"]), mask_sensitive_data(result["verification"]))
    save_json(Path(output_paths["analysis_output_path"]), mask_sensitive_data(result["verification"]["analysis"]))


def _attach_rag_analysis(result: dict, run_dir: Path, output_paths: dict) -> None:
    try:
        log_step(15, "RAG 검색 및 법령·가이드 근거 수집 중")
        rag_result = analyze_contract_with_rag(mask_sensitive_data(result["extracted"]), output_dir=run_dir)
        result["rag_analysis"] = {
            "status": rag_result["status"],
            "embedding_model": rag_result["embedding_model"],
            "analysis_model": rag_result["analysis_model"],
            "summary": rag_result["analysis_result"],
        }
        output_paths.update(rag_result.get("output_paths", {}))
        log_step(16, "RAG 최종 분석 저장 완료")
    except Exception as exc:
        result["rag_analysis"] = {
            "status": "failed",
            "error_message": str(exc),
        }
        log_step(16, f"RAG 분석 실패: {exc}")


def _build_highlight_summary(result: dict, source_pdf_path: str | None, run_dir: Path, output_paths: dict) -> dict:
    rag_summary = None
    if (result.get("rag_analysis") or {}).get("status") == "success":
        rag_summary = (result.get("rag_analysis") or {}).get("summary")

    if not source_pdf_path:
        return {
            "summary": result["verification"]["analysis"]["summary"],
            "rag_summary": rag_summary or {},
            "highlights": [],
        }

    log_step(17, "PDF 하이라이트 및 미리보기 이미지 생성 중")
    highlight_result = generate_finding_highlight_artifacts(
        pdf_path=source_pdf_path,
        extracted=result["extracted"],
        verification_summary=result["verification"],
        rag_summary=rag_summary,
        output_dir=run_dir,
    )
    output_paths.update(highlight_result)
    return {
        "summary": result["verification"]["analysis"]["summary"],
        "rag_summary": rag_summary or {},
        "highlights": highlight_result.get("highlights", []),
    }


def persist_verification_outputs(result: dict, source_pdf_path: str | None = None) -> dict:
    run_dir = build_output_run_dir()
    output_paths = _build_base_output_paths(run_dir)
    _save_base_outputs(result, output_paths)
    _attach_rag_analysis(result, run_dir, output_paths)
    result["highlight_summary"] = _build_highlight_summary(result, source_pdf_path, run_dir, output_paths)
    save_json(Path(output_paths["combined_output_path"]), build_public_result(result))
    log_step(18, f"검증 파이프라인 완료: {run_dir}")
    return output_paths

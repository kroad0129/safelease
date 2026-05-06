import json
import sys
from pathlib import Path

from app.core.common import SAMPLE_PDF_PATH
from app.services.contract_service import verify_contract_path


def resolve_input_pdf_path() -> str:
    if len(sys.argv) > 1:
        return str(Path(sys.argv[1]).resolve())
    return str(SAMPLE_PDF_PATH)


def main():
    pdf_path = resolve_input_pdf_path()

    if not SAMPLE_PDF_PATH.exists() and len(sys.argv) == 1:
        raise FileNotFoundError(f"sample.pdf 파일을 찾을 수 없습니다: {SAMPLE_PDF_PATH}")

    print("=== 계약서 검증 시작 ===")
    result = verify_contract_path(pdf_path)
    output_paths = result.get("output_paths", {})
    verification = result["verification"]
    rule_summary = verification["analysis"]["summary"]
    rag_analysis = result.get("rag_analysis") or {}

    print("\n=== 검증 완료 ===")
    print("\n[규칙 기반 요약]")
    print(
        json.dumps(
            {
                "overall_status": rule_summary["overall_status"],
                "review_level": rule_summary["review_level"],
                "error_count": rule_summary["error_count"],
                "warning_count": rule_summary["warning_count"],
                "finding_count": rule_summary["finding_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if rag_analysis.get("status") == "success":
        overall_summary = (rag_analysis.get("summary") or {}).get("overall_summary") or {}
        print("\n[RAG 기반 요약]")
        print(
            json.dumps(
                {
                    "key_risks": overall_summary.get("key_risks", []),
                    "key_strengths": overall_summary.get("key_strengths", []),
                    "recommended_next_actions": overall_summary.get("recommended_next_actions", []),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif rag_analysis.get("status") == "failed":
        print("\n[RAG 기반 요약]")
        print(
            json.dumps(
                {"status": "failed", "error_message": rag_analysis.get("error_message")},
                ensure_ascii=False,
                indent=2,
            )
        )

    print(f"\n실행 결과 폴더: {output_paths['run_dir']}")
    print(f"\n추출 결과 저장: {output_paths['extracted_output_path']}")
    print(f"검증 결과 저장: {output_paths['verification_output_path']}")
    print(f"분석 결과 저장: {output_paths['analysis_output_path']}")
    print(f"통합 결과 저장: {output_paths['combined_output_path']}")
    if "highlighted_pdf_path" in output_paths:
        print(f"하이라이트 PDF 저장: {output_paths['highlighted_pdf_path']}")
        print(f"하이라이트 JSON 저장: {output_paths['highlight_json_path']}")
    if "rag_result_path" in output_paths:
        print(f"RAG 검색 결과 저장: {output_paths['rag_result_path']}")
    if "rag_payload_path" in output_paths:
        print(f"RAG LLM payload 저장: {output_paths['rag_payload_path']}")
    if "rag_analysis_path" in output_paths:
        print(f"RAG 최종 분석 저장: {output_paths['rag_analysis_path']}")

    print("\n[전체 결과 JSON]")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

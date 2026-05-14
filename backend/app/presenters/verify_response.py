from pathlib import Path

from app.core.common import OUTPUT_DIR
from app.services.privacy_masking import build_public_result


def build_public_output_url(path_str: str | None) -> str | None:
    if not path_str:
        return None

    path = Path(path_str).resolve()
    outputs_root = OUTPUT_DIR.resolve()
    try:
        relative = path.relative_to(outputs_root)
    except ValueError:
        return None
    return f"/outputs/{relative.as_posix()}"


def build_review_payload(result: dict, highlight_summary: dict) -> dict:
    verification = result["verification"]
    analysis = verification["analysis"]
    summary = analysis["summary"]
    findings = analysis["findings"]

    if summary["review_level"] == "주의":
        headline = "주의가 필요한 계약서입니다."
    elif summary["review_level"] == "보통":
        headline = "몇 가지 확인이 더 필요한 계약서입니다."
    else:
        headline = "현재 기준으로는 비교적 양호한 계약서입니다."

    finding_messages = [f"- {finding['title']}: {finding['message']}" for finding in findings[:5]]
    if not finding_messages:
        finding_messages.append("- 현재 자동 검증에서 주요 이상 징후는 확인되지 않았습니다.")

    passed_checks = []
    for field_path in ("property.address", "lessor.address", "lessee.address", "broker.registration_number"):
        if any(
            item.get("field_path") == field_path and item.get("review_level") == "양호"
            for item in highlight_summary.get("highlights", [])
        ):
            passed_checks.append(field_path)

    review_text = "\n".join(
        [
            headline,
            "",
            "검토 요약",
            f"- 전체 판정: {summary['review_level']}",
            f"- 오류 {summary['error_count']}건, 경고 {summary['warning_count']}건",
            "",
            "주요 포인트",
            *finding_messages,
        ]
    )

    return {
        "headline": headline,
        "reviewLevel": summary["review_level"],
        "reviewText": review_text,
        "findingCount": summary["finding_count"],
        "passedChecks": passed_checks,
        "inputSummary": verification["input_summary"],
    }


def build_rag_payload(result: dict) -> dict | None:
    rag_analysis = result.get("rag_analysis")
    if not rag_analysis:
        return None

    payload = {
        "status": rag_analysis.get("status"),
        "embeddingModel": rag_analysis.get("embedding_model"),
        "analysisModel": rag_analysis.get("analysis_model"),
        "summary": rag_analysis.get("summary"),
    }
    if rag_analysis.get("error_message"):
        payload["errorMessage"] = rag_analysis["error_message"]
    return payload


def build_rag_review_payload(result: dict) -> dict | None:
    rag_analysis = result.get("rag_analysis") or {}
    if rag_analysis.get("status") != "success":
        if rag_analysis.get("error_message"):
            return {
                "status": "failed",
                "headline": "법령 근거 분석을 완료하지 못했습니다.",
                "summaryText": rag_analysis["error_message"],
                "keyRisks": [],
                "keyStrengths": [],
                "recommendedNextActions": [],
            }
        return None

    summary = rag_analysis.get("summary") or {}
    overall = summary.get("overall_summary") or {}
    key_risks = overall.get("key_risks") or []
    key_strengths = overall.get("key_strengths") or []
    next_actions = overall.get("recommended_next_actions") or []
    contract_conditions = summary.get("contract_conditions") or []
    special_terms = summary.get("special_terms") or []
    has_caution_items = any(item.get("review_level") == "주의" for item in [*contract_conditions, *special_terms])
    has_verification_errors = ((result.get("verification") or {}).get("analysis") or {}).get("summary", {}).get("error_count", 0) > 0

    if key_risks and (has_verification_errors or has_caution_items):
        headline = "고쳐야 할 부분이 있는 계약서입니다."
        summary_text = "기간, 보증금 반환, 수리비 부담처럼 분쟁으로 이어질 수 있는 항목을 먼저 확인하세요."
    elif key_risks:
        headline = "서명 전 확인할 부분이 있는 계약서입니다."
        summary_text = "큰 문제로 단정되지는 않지만, 기간과 금액, 권리관계처럼 분쟁을 줄이는 항목을 한 번 더 확인하세요."
    elif key_strengths:
        headline = "큰 위험은 적고, 일부 조건은 임차인에게 도움이 됩니다."
        summary_text = "다만 서명 전에는 날짜, 금액, 권리관계처럼 기본 항목을 한 번 더 확인하는 것이 좋습니다."
    else:
        headline = "계약서 종합 요약이 완료되었습니다."
        summary_text = "계약조건과 특약을 기준으로 주요 확인사항을 정리했습니다."

    return {
        "status": "success",
        "headline": headline,
        "summaryText": summary_text,
        "keyRisks": key_risks,
        "keyStrengths": key_strengths,
        "recommendedNextActions": next_actions,
        "contractConditionCount": len(contract_conditions),
        "specialTermCount": len(special_terms),
    }


def build_verify_response_payload_from_public_result(public_result: dict, output_paths: dict) -> dict:
    highlight_summary = public_result.get("highlight_summary", {})

    payload = {
        "result": public_result,
        "outputPaths": output_paths,
        "artifacts": {
            "highlightedPdfUrl": build_public_output_url(output_paths.get("highlighted_pdf_path")),
            "highlightedImageUrl": build_public_output_url(output_paths.get("highlighted_png_path")),
            "renderedImageUrl": build_public_output_url(output_paths.get("rendered_png_path")),
            "extractionJsonUrl": build_public_output_url(output_paths.get("extraction_path")),
            "highlightJsonUrl": build_public_output_url(output_paths.get("highlight_json_path")),
            "analysisJsonUrl": build_public_output_url(output_paths.get("analysis_output_path")),
            "verificationJsonUrl": build_public_output_url(output_paths.get("verification_output_path")),
            "combinedResultJsonUrl": build_public_output_url(output_paths.get("combined_output_path")),
            "ragResultJsonUrl": build_public_output_url(output_paths.get("rag_result_path")),
            "ragPayloadJsonUrl": build_public_output_url(output_paths.get("rag_payload_path")),
            "ragAnalysisJsonUrl": build_public_output_url(output_paths.get("rag_analysis_path")),
        },
        "highlightSummary": highlight_summary,
    }
    payload["review"] = build_review_payload(public_result, highlight_summary)
    payload["ragAnalysis"] = build_rag_payload(public_result)
    payload["ragReview"] = build_rag_review_payload(public_result)
    return payload


def build_verify_response_payload(result: dict) -> dict:
    public_result = build_public_result(result)
    output_paths = result.get("output_paths", {})
    return build_verify_response_payload_from_public_result(public_result, output_paths)

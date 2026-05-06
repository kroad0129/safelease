from app.services.contract_normalizer import normalize_space

STATUS_LABELS = {
    "property_address": "소재지",
    "lessor_address": "임대인 주소",
    "lessee_address": "임차인 주소",
    "broker": "중개업 등록번호",
}


def severity_to_review_level(severity: str) -> str:
    if severity == "error":
        return "주의"
    if severity == "warning":
        return "보통"
    return "양호"


def build_finding(
    code: str,
    severity: str,
    title: str,
    message: str,
    field_path: str,
    category: str,
    status: str,
    evidence: dict | None = None,
) -> dict:
    return {
        "code": code,
        "severity": severity,
        "title": title,
        "message": message,
        "field_path": field_path,
        "category": category,
        "status": status,
        "review_level": severity_to_review_level(severity),
        "evidence": evidence or {},
    }


def normalize_compare_text(text: str | None) -> str | None:
    text = normalize_space(text)
    if not text:
        return None
    normalized = text.lower()
    for token in (" ", "(", ")", "-", ".", ","):
        normalized = normalized.replace(token, "")
    return normalized


def addresses_roughly_match(left: str | None, right: str | None) -> bool:
    left_normalized = normalize_compare_text(left)
    right_normalized = normalize_compare_text(right)

    if not left_normalized or not right_normalized:
        return False

    return (
        left_normalized == right_normalized
        or left_normalized in right_normalized
        or right_normalized in left_normalized
    )


def build_status_finding_prefix(label: str, result: dict, field_path: str) -> dict | None:
    status = result.get("status")
    error_message = result.get("error_message")
    error_code = result.get("error_code")
    display_label = STATUS_LABELS.get(label, label)

    if status == "success":
        return None

    if status == "not_found":
        return build_finding(
            code=f"{label.upper()}_NOT_FOUND",
            severity="error",
            title=f"{display_label} 조회 결과 없음",
            message=error_message or f"{display_label}를 확인할 수 있는 조회 결과를 찾지 못했습니다.",
            field_path=field_path,
            category="verification",
            status="fail",
            evidence={"error_code": error_code},
        )

    if status == "partial_match":
        return build_finding(
            code=f"{label.upper()}_PARTIAL_MATCH",
            severity="warning",
            title=f"{display_label} 일부 확인",
            message=error_message or f"{display_label}는 일부만 확인되었습니다.",
            field_path=field_path,
            category="verification",
            status="warning",
            evidence={"error_code": error_code},
        )

    return build_finding(
        code=f"{label.upper()}_QUERY_FAILED",
        severity="error",
        title=f"{display_label} 조회 실패",
        message=error_message or f"{display_label} 조회 중 오류가 발생했습니다.",
        field_path=field_path,
        category="verification",
        status="fail",
        evidence={"error_code": error_code},
    )


def analyze_property_address_verification(findings: list[dict], result: dict) -> None:
    status = result.get("status")
    data = result.get("data") or {}

    if status == "success":
        return

    road_exists = bool(data.get("road"))
    detail_available = data.get("detail_available")
    detail_match = data.get("detail_match")
    error_message = result.get("error_message")
    error_code = result.get("error_code")

    if road_exists and detail_available and detail_match is False:
        findings.append(
            build_finding(
                code="PROPERTY_LEASED_PART_NOT_FOUND",
                severity="error",
                title="임대할부분 불일치",
                message=error_message or "기본주소는 확인되었지만 동/층/호와 일치하는 상세주소를 찾지 못했습니다.",
                field_path="property.leased_part.raw_text",
                category="verification",
                status="fail",
                evidence={"error_code": error_code},
            )
        )
        return

    if road_exists and detail_available is False:
        findings.append(
            build_finding(
                code="PROPERTY_LEASED_PART_PARTIAL_MATCH",
                severity="warning",
                title="임대할부분 일부 확인",
                message=error_message or "기본주소는 확인되었지만 상세주소 목록을 확인하지 못했습니다.",
                field_path="property.leased_part.raw_text",
                category="verification",
                status="warning",
                evidence={"error_code": error_code},
            )
        )
        return

    finding = build_status_finding_prefix(
        label="property_address",
        result=result,
        field_path="property.address",
    )
    if finding:
        findings.append(finding)


def analyze_address_field(findings: list[dict], label: str, address: str | None, field_path: str) -> None:
    if address:
        return
    findings.append(
        build_finding(
            code=f"{label.upper()}_ADDRESS_MISSING",
            severity="error",
            title=f"{label} 주소 누락",
            message=f"{label} 주소가 계약서에서 추출되지 않았습니다.",
            field_path=field_path,
            category="extraction",
            status="fail",
        )
    )


def analyze_broker_consistency(findings: list[dict], normalized: dict, broker_result: dict) -> None:
    broker_input = normalized["broker"]
    broker_data = broker_result.get("data") or {}

    input_reg = broker_input.get("registration_number")
    actual_reg = broker_data.get("registration_number")
    if input_reg and actual_reg and normalize_compare_text(input_reg) != normalize_compare_text(actual_reg):
        findings.append(
            build_finding(
                code="BROKER_REGISTRATION_MISMATCH",
                severity="error",
                title="중개업 등록번호 불일치",
                message="계약서의 중개업 등록번호와 조회 결과의 등록번호가 다릅니다.",
                field_path="broker.registration_number",
                category="consistency",
                status="fail",
                evidence={"input": input_reg, "actual": actual_reg},
            )
        )

    input_rep = broker_input.get("representative_name")
    actual_rep = broker_data.get("representative_name")
    if input_rep and actual_rep and normalize_compare_text(input_rep) != normalize_compare_text(actual_rep):
        findings.append(
            build_finding(
                code="BROKER_REPRESENTATIVE_MISMATCH",
                severity="error",
                title="중개업 대표자 불일치",
                message="계약서의 대표자명과 중개업 조회 결과의 대표자명이 다릅니다.",
                field_path="broker.representative_name",
                category="consistency",
                status="fail",
                evidence={"input": input_rep, "actual": actual_rep},
            )
        )

    input_name = broker_input.get("office_name")
    actual_name = broker_data.get("office_name")
    if input_name and actual_name and normalize_compare_text(input_name) != normalize_compare_text(actual_name):
        findings.append(
            build_finding(
                code="BROKER_OFFICE_NAME_MISMATCH",
                severity="warning",
                title="중개업 상호 불일치",
                message="계약서의 중개업 상호와 조회 결과의 상호가 다릅니다.",
                field_path="broker.office_name",
                category="consistency",
                status="warning",
                evidence={"input": input_name, "actual": actual_name},
            )
        )

    input_address = broker_input.get("office_address")
    actual_address = broker_data.get("office_address")
    if input_address and actual_address and not addresses_roughly_match(input_address, actual_address):
        findings.append(
            build_finding(
                code="BROKER_OFFICE_ADDRESS_MISMATCH",
                severity="warning",
                title="중개업 소재지 불일치",
                message="계약서의 중개업 소재지와 조회 결과의 소재지가 다릅니다.",
                field_path="broker.office_address",
                category="consistency",
                status="warning",
                evidence={"input": input_address, "actual": actual_address},
            )
        )


def analyze_rent_reference(findings: list[dict], rent_reference_result: dict) -> None:
    if rent_reference_result.get("status") != "success":
        return

    data = rent_reference_result.get("data") or {}
    comparison = data.get("comparison") or {}
    if comparison.get("level") != "warning":
        return

    contract_value = (data.get("contractConvertedMonthlyRent") or {}).get("value")
    reference = data.get("reference") or {}
    normal_range = reference.get("normalRange") or {}
    p90 = reference.get("p90ConvertedMonthlyRent") or {}

    findings.append(
        build_finding(
            code="RENT_REFERENCE_HIGH",
            severity="warning",
            title="임대료 참고 범위 초과",
            message=comparison.get("message") or "계약 환산월세가 참고 임대료 범위보다 높습니다.",
            field_path="payment.monthly_rent",
            category="market_reference",
            status="warning",
            evidence={
                "contract_converted_monthly_rent_manwon": contract_value,
                "normal_range_manwon": {
                    "min": normal_range.get("min"),
                    "max": normal_range.get("max"),
                },
                "p90_converted_monthly_rent_manwon": p90.get("value"),
                "basis": reference.get("basis"),
                "sample_count": reference.get("sampleCount"),
                "fallback_used": reference.get("fallbackUsed"),
            },
        )
    )


def build_document_overview(extracted: dict) -> dict:
    contract_terms = extracted.get("contract_terms") or []
    special_terms = extracted.get("special_terms") or []

    return {
        "contract_term_count": len(contract_terms),
        "special_term_count": len(special_terms),
        "has_special_terms": len(special_terms) > 0,
    }


def summarize_findings(findings: list[dict]) -> dict:
    error_count = sum(1 for finding in findings if finding["severity"] == "error")
    warning_count = sum(1 for finding in findings if finding["severity"] == "warning")
    info_count = sum(1 for finding in findings if finding["severity"] == "info")

    if error_count > 0:
        overall_status = "fail"
    elif warning_count > 0:
        overall_status = "warning"
    else:
        overall_status = "pass"

    return {
        "overall_status": overall_status,
        "review_level": severity_to_review_level("error" if error_count > 0 else "warning" if warning_count > 0 else "info"),
        "error_count": error_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "finding_count": len(findings),
    }


def build_analysis(extracted: dict, normalized: dict, verification_summary: dict) -> dict:
    findings: list[dict] = []

    analyze_address_field(findings, "property", normalized["property"].get("address"), "property.address")
    analyze_address_field(findings, "lessor", normalized["lessor"].get("address"), "lessor.address")
    analyze_address_field(findings, "lessee", normalized["lessee"].get("address"), "lessee.address")

    analyze_property_address_verification(findings, verification_summary["address_verification"])

    for label, field_path, result_key in (
        ("lessor_address", "lessor.address", "lessor_address_verification"),
        ("lessee_address", "lessee.address", "lessee_address_verification"),
        ("broker", "broker.registration_number", "broker_verification"),
    ):
        finding = build_status_finding_prefix(
            label=label,
            result=verification_summary[result_key],
            field_path=field_path,
        )
        if finding:
            findings.append(finding)

    broker_input = normalized["broker"]
    if not broker_input.get("registration_number"):
        findings.append(
            build_finding(
                code="BROKER_REGISTRATION_NUMBER_MISSING",
                severity="error",
                title="중개업 등록번호 누락",
                message="계약서에서 중개업 등록번호를 추출하지 못했습니다.",
                field_path="broker.registration_number",
                category="extraction",
                status="fail",
            )
        )

    if not broker_input.get("representative_name"):
        findings.append(
            build_finding(
                code="BROKER_REPRESENTATIVE_NAME_MISSING",
                severity="warning",
                title="중개업 대표자명 누락",
                message="계약서에서 중개업 대표자명을 추출하지 못했습니다.",
                field_path="broker.representative_name",
                category="extraction",
                status="warning",
            )
        )

    if verification_summary["broker_verification"].get("status") == "success":
        analyze_broker_consistency(findings, normalized, verification_summary["broker_verification"])

    analyze_rent_reference(findings, verification_summary.get("rent_reference_verification") or {})

    return {
        "document_overview": build_document_overview(extracted),
        "summary": summarize_findings(findings),
        "findings": findings,
    }

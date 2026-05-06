from app.core.common import build_result
from app.core.progress import log_step
from app.services.contract_extractor import extract_contract_from_pdf, upload_file
from app.services.contract_normalizer import normalize_contract_for_validation
from app.services.rent_reference_service import verify_rent_reference
from app.services.verification_analysis import build_analysis
from app.validators.address_validator import verify_address
from app.validators.broker_validator import BrokerSearchInput, search_broker


def build_verification_summary(
    normalized: dict,
    extracted: dict,
    property_address_result: dict,
    lessor_address_result: dict,
    lessee_address_result: dict,
    broker_result: dict,
    rent_reference_result: dict,
) -> dict:
    summary = {
        "input_summary": normalized,
        "address_verification": property_address_result,
        "lessor_address_verification": lessor_address_result,
        "lessee_address_verification": lessee_address_result,
        "broker_verification": broker_result,
        "rent_reference_verification": rent_reference_result,
    }
    summary["analysis"] = build_analysis(
        extracted=extracted,
        normalized=normalized,
        verification_summary=summary,
    )
    return summary


def build_missing_address_result() -> dict:
    return build_result(
        status="query_failed",
        error_code="ADDRESS_MISSING",
        error_message="계약서에서 주소를 추출하지 못했습니다.",
    )


def build_missing_party_address_result(role_label: str) -> dict:
    return build_result(
        status="query_failed",
        error_code="ADDRESS_MISSING",
        error_message=f"계약서에서 {role_label} 주소를 추출하지 못했습니다.",
    )


def build_missing_broker_result(broker_info: dict) -> dict:
    return build_result(
        status="query_failed",
        error_code="BROKER_INPUT_MISSING",
        error_message="중개사 조회에 필요한 시도/시군구/등록번호가 부족합니다.",
        debug={
            "sido": broker_info["sido"],
            "sigungu": broker_info["sigungu"],
            "registration_number": broker_info["registration_number"],
            "office_address": broker_info["office_address"],
        },
    )


def verify_simple_address(address: str | None, role_label: str) -> dict:
    if not address:
        return build_missing_party_address_result(role_label)
    return verify_address(base_address=address, leased_part="")


def verify_contract_pdf(pdf_path: str) -> dict:
    log_step(1, f"계약서 검증 시작: {pdf_path}")
    file_id = upload_file(pdf_path)
    extracted = extract_contract_from_pdf(file_id)
    log_step(8, "추출 결과 정규화 및 검증 입력 생성 중")
    normalized = normalize_contract_for_validation(extracted)

    property_info = normalized["property"]
    lessor_info = normalized["lessor"]
    lessee_info = normalized["lessee"]
    broker_info = normalized["broker"]

    if property_info["address"]:
        log_step(9, "목적물 주소 및 상세주소 검증 중")
        property_address_result = verify_address(
            base_address=property_info["address"],
            leased_part=property_info["leased_part_raw"] or "",
        )
    else:
        log_step(9, "목적물 주소 누락으로 주소 검증 건너뜀")
        property_address_result = build_missing_address_result()

    log_step(10, "임대인/임차인 주소 검증 중")
    lessor_address_result = verify_simple_address(lessor_info["address"], "임대인")
    lessee_address_result = verify_simple_address(lessee_info["address"], "임차인")

    if broker_info["sido"] and broker_info["sigungu"] and broker_info["registration_number"]:
        log_step(11, "중개업 등록번호 조회 중")
        broker_result = search_broker(
            BrokerSearchInput(
                sido=broker_info["sido"],
                sigungu=broker_info["sigungu"],
                registration_number=broker_info["registration_number"],
            )
        )
    else:
        log_step(11, "중개업 조회 입력 부족으로 조회 건너뜀")
        broker_result = build_missing_broker_result(broker_info)

    log_step(12, "임대료 참고 시세 비교 중")
    rent_reference_result = verify_rent_reference(
        extracted=extracted,
        property_address_result=property_address_result,
    )

    log_step(13, "규칙 기반 검증 결과 종합 중")
    return {
        "extracted": extracted,
        "verification": build_verification_summary(
            normalized=normalized,
            extracted=extracted,
            property_address_result=property_address_result,
            lessor_address_result=lessor_address_result,
            lessee_address_result=lessee_address_result,
            broker_result=broker_result,
            rent_reference_result=rent_reference_result,
        ),
    }

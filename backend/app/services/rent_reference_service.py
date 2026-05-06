import os
import re
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.core.common import build_result, load_project_env


DEFAULT_CONVERSION_RATE = 0.045
MIN_DONG_AREA_SAMPLE = 10


def get_connection_string() -> str:
    load_project_env()
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5433")
    dbname = os.getenv("POSTGRES_DB", "rent")
    user = os.getenv("POSTGRES_USER", "rent")
    password = os.getenv("POSTGRES_PASSWORD", "rent1234")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def area_band(area_m2: float) -> str:
    if area_m2 < 20:
        return "lt_20"
    if area_m2 < 30:
        return "gte_20_lt_30"
    if area_m2 < 40:
        return "gte_30_lt_40"
    if area_m2 < 50:
        return "gte_40_lt_50"
    if area_m2 < 60:
        return "gte_50_lt_60"
    if area_m2 < 85:
        return "gte_60_lt_85"
    return "gte_85"


def area_band_label(band: str) -> str:
    labels = {
        "lt_20": "20㎡ 미만",
        "gte_20_lt_30": "20㎡ 이상~30㎡ 미만",
        "gte_30_lt_40": "30㎡ 이상~40㎡ 미만",
        "gte_40_lt_50": "40㎡ 이상~50㎡ 미만",
        "gte_50_lt_60": "50㎡ 이상~60㎡ 미만",
        "gte_60_lt_85": "60㎡ 이상~85㎡ 미만",
        "gte_85": "85㎡ 이상",
    }
    return labels.get(band, band)


def extract_dong_from_jibun(jibun_address: str | None) -> str | None:
    if not jibun_address:
        return None
    match = re.search(r"\s([0-9A-Za-z가-힣]+동)\s", f" {jibun_address} ")
    return match.group(1) if match else None


def extract_reference_location(address_result: dict) -> dict:
    data = address_result.get("data") or {}
    road = data.get("road") or {}
    adm_cd = road.get("admCd")
    jibun_address = road.get("jibunAddr")

    return {
        "sgg_cd": adm_cd[:5] if adm_cd else None,
        "legal_dong_cd": adm_cd[:10] if adm_cd else None,
        "umd_nm": extract_dong_from_jibun(jibun_address),
        "jibun_address": jibun_address,
    }


def get_nested_value(data: dict, *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def extract_contract_rent_inputs(extracted: dict) -> dict:
    area = (
        get_nested_value(extracted, "property", "leased_part", "area_m2", "normalized_value")
        or get_nested_value(extracted, "property", "building", "area_m2", "normalized_value")
    )
    deposit = get_nested_value(extracted, "payment", "deposit", "normalized_value")
    monthly_rent = get_nested_value(extracted, "payment", "monthly_rent", "normalized_value")

    return {
        "area_m2": to_float(area),
        "deposit_won": to_float(deposit),
        "monthly_rent_won": to_float(monthly_rent) or 0.0,
    }


def converted_monthly_rent_manwon(
    deposit_won: float,
    monthly_rent_won: float,
    conversion_rate: float = DEFAULT_CONVERSION_RATE,
) -> float:
    deposit_manwon = deposit_won / 10000
    monthly_rent_manwon = monthly_rent_won / 10000
    return monthly_rent_manwon + (deposit_manwon * conversion_rate / 12)


def row_to_reference(row: dict, fallback_used: bool) -> dict:
    sample_count = int(row["sample_count"])
    return {
        "basis": row["basis"],
        "fallbackUsed": fallback_used,
        "confidence": "strong" if sample_count >= 30 else "weak",
        "sampleCount": sample_count,
        "normalRange": {
            "min": to_float(row["p25_converted_monthly_rent"]),
            "max": to_float(row["p75_converted_monthly_rent"]),
            "unit": "만원",
        },
        "medianConvertedMonthlyRent": {
            "value": to_float(row["median_converted_monthly_rent"]),
            "unit": "만원",
        },
        "p90ConvertedMonthlyRent": {
            "value": to_float(row["p90_converted_monthly_rent"]),
            "unit": "만원",
        },
        "medianDeposit": {
            "value": to_float(row["median_deposit_manwon"]),
            "unit": "만원",
        },
        "medianMonthlyRentForMonthlyContractsOnly": {
            "value": to_float(row["median_monthly_rent_wolse_only"]) or 0.0,
            "unit": "만원",
        },
        "medianAreaM2": to_float(row["median_area_m2"]),
    }


def fetch_reference_stats(location: dict, band: str) -> dict | None:
    sgg_cd = location.get("sgg_cd")
    legal_dong_cd = location.get("legal_dong_cd")
    umd_nm = location.get("umd_nm")

    if not sgg_cd:
        return None

    with psycopg.connect(get_connection_string(), row_factory=dict_row) as conn:
        rows = conn.execute(
            """
            select *
            from rent_reference_stats
            where sgg_cd = %(sgg_cd)s
              and (
                (basis = 'dong_area' and area_band = %(band)s and (legal_dong_cd = %(legal_dong_cd)s or umd_nm = %(umd_nm)s))
                or (basis = 'area' and area_band = %(band)s)
                or (basis = 'dong' and (legal_dong_cd = %(legal_dong_cd)s or umd_nm = %(umd_nm)s))
                or basis = 'region'
              )
            """,
            {
                "sgg_cd": sgg_cd,
                "band": band,
                "legal_dong_cd": legal_dong_cd,
                "umd_nm": umd_nm,
            },
        ).fetchall()

    by_basis = {row["basis"]: dict(row) for row in rows}
    dong_area = by_basis.get("dong_area")
    if dong_area and int(dong_area["sample_count"]) >= MIN_DONG_AREA_SAMPLE:
        return row_to_reference(dong_area, fallback_used=False)
    if by_basis.get("area"):
        return row_to_reference(by_basis["area"], fallback_used=True)
    if by_basis.get("dong"):
        return row_to_reference(by_basis["dong"], fallback_used=True)
    if by_basis.get("region"):
        return row_to_reference(by_basis["region"], fallback_used=True)
    return None


def compare_to_reference(contract_value: float, reference: dict) -> dict:
    normal_min = reference["normalRange"]["min"]
    normal_max = reference["normalRange"]["max"]
    p90 = reference["p90ConvertedMonthlyRent"]["value"]

    if p90 is not None and contract_value > p90:
        status = "high"
        level = "warning"
        message = "계약 환산월세가 같은 지역·면적 참고값의 상위 10% 기준보다 높습니다."
    elif normal_max is not None and contract_value > normal_max:
        status = "slightly_high"
        level = "warning"
        message = "계약 환산월세가 일반적인 참고 범위 상단보다 높습니다."
    elif normal_min is not None and contract_value < normal_min:
        status = "low"
        level = "info"
        message = "계약 환산월세가 일반적인 참고 범위 하단보다 낮습니다."
    else:
        status = "normal"
        level = "info"
        message = "계약 환산월세가 일반적인 참고 범위 안에 있습니다."

    return {
        "status": status,
        "level": level,
        "message": message,
    }


def verify_rent_reference(extracted: dict, property_address_result: dict) -> dict:
    rent_inputs = extract_contract_rent_inputs(extracted)
    area = rent_inputs["area_m2"]
    deposit = rent_inputs["deposit_won"]
    monthly_rent = rent_inputs["monthly_rent_won"]

    if area is None or area <= 0:
        return build_result(
            status="query_failed",
            error_code="RENT_AREA_MISSING",
            error_message="계약서에서 임대 면적을 추출하지 못해 참고 임대료를 비교할 수 없습니다.",
            debug={"input": rent_inputs},
        )
    if deposit is None:
        return build_result(
            status="query_failed",
            error_code="RENT_DEPOSIT_MISSING",
            error_message="계약서에서 보증금을 추출하지 못해 참고 임대료를 비교할 수 없습니다.",
            debug={"input": rent_inputs},
        )

    location = extract_reference_location(property_address_result)
    band = area_band(area)
    reference = fetch_reference_stats(location, band)
    if not reference:
        return build_result(
            status="not_found",
            error_code="RENT_REFERENCE_NOT_FOUND",
            error_message="해당 주소와 면적에 맞는 참고 임대료 통계를 찾지 못했습니다.",
            debug={"location": location, "area_band": band, "input": rent_inputs},
        )

    contract_value = converted_monthly_rent_manwon(deposit, monthly_rent)
    comparison = compare_to_reference(contract_value, reference)

    return build_result(
        status="success",
        data={
            "input": {
                "sggCd": location["sgg_cd"],
                "legalDongCd": location["legal_dong_cd"],
                "umdNm": location["umd_nm"],
                "jibunAddress": location["jibun_address"],
                "area": area,
                "areaUnit": "㎡",
                "areaBand": band,
                "areaBandLabel": area_band_label(band),
                "deposit": deposit,
                "monthlyRent": monthly_rent,
                "moneyUnit": "원",
            },
            "contractConvertedMonthlyRent": {
                "value": round(contract_value, 1),
                "unit": "만원",
            },
            "reference": reference,
            "comparison": comparison,
            "meta": {
                "dataSource": "rent_reference_stats",
                "conversionRate": DEFAULT_CONVERSION_RATE,
                "formula": "환산월세(만원) = 월세금(만원) + 보증금(만원) * 0.045 / 12",
            },
        },
    )

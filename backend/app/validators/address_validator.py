import json
import re

import requests

from app.core.common import build_result, get_required_env, load_project_env


load_project_env()
JUSO_ROAD_API_KEY = get_required_env("JUSO_ROAD_API_KEY")
JUSO_DETAIL_API_KEY = get_required_env("JUSO_DETAIL_API_KEY")


JUSO_ROAD_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
JUSO_DETAIL_URL = "https://business.juso.go.kr/addrlink/addrDetailApi.do"


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(str(text).strip().split())


def parse_leased_part(leased_part: str) -> dict:
    text = normalize_text(leased_part)

    dong_match = re.search(r"([0-9A-Za-z가-힣]+동)", text)
    floor_match = re.search(r"([0-9A-Za-z가-힣]+층)", text)
    ho_match = re.search(r"([0-9A-Za-z가-힣]+호)", text)

    return {
        "raw": text,
        "dong": dong_match.group(1) if dong_match else None,
        "floor": floor_match.group(1) if floor_match else None,
        "ho": ho_match.group(1) if ho_match else None,
    }


def search_road_address(keyword: str) -> dict:
    params = {
        "confmKey": JUSO_ROAD_API_KEY,
        "currentPage": "1",
        "countPerPage": "10",
        "resultType": "json",
        "keyword": keyword,
    }

    resp = requests.get(JUSO_ROAD_URL, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def parse_road_result(road_result: dict) -> dict:
    results = road_result.get("results", {})
    common = results.get("common", {})
    juso_list = results.get("juso", [])

    if common.get("errorCode") != "0":
        return build_result(
            status="query_failed",
            error_code=common.get("errorCode"),
            error_message=common.get("errorMessage"),
            debug={"raw_common": common},
        )

    if not juso_list:
        return build_result(
            status="not_found",
            error_code="ROAD_NOT_FOUND",
            error_message="도로명주소 검색 결과가 없습니다.",
            debug={"raw_common": common},
        )

    best = juso_list[0]

    parsed = {
        "roadAddr": best.get("roadAddr"),
        "roadAddrPart1": best.get("roadAddrPart1"),
        "roadAddrPart2": best.get("roadAddrPart2"),
        "jibunAddr": best.get("jibunAddr"),
        "zipNo": best.get("zipNo"),
        "admCd": best.get("admCd"),
        "rnMgtSn": best.get("rnMgtSn"),
        "udrtYn": best.get("udrtYn"),
        "buldMnnm": best.get("buldMnnm"),
        "buldSlno": best.get("buldSlno"),
        "bdMgtSn": best.get("bdMgtSn"),
        "bdNm": best.get("bdNm"),
        "detBdNmList": best.get("detBdNmList"),
    }

    return build_result(
        status="success",
        data=parsed,
        debug={
            "candidate_count": len(juso_list),
            "totalCount": common.get("totalCount"),
        },
    )


def search_detail_address(
    adm_cd: str,
    rn_mgt_sn: str,
    udrt_yn: str,
    buld_mnnm: str,
    buld_slno: str,
    dong_nm: str = "",
    search_type: str = "floorho",
) -> dict:
    params = {
        "confmKey": JUSO_DETAIL_API_KEY,
        "resultType": "json",
        "admCd": adm_cd,
        "rnMgtSn": rn_mgt_sn,
        "udrtYn": udrt_yn,
        "buldMnnm": buld_mnnm,
        "buldSlno": buld_slno,
        "searchType": search_type,
        "dongNm": dong_nm,
    }

    resp = requests.get(JUSO_DETAIL_URL, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def parse_detail_result(detail_result: dict) -> dict:
    results = detail_result.get("results", {})
    common = results.get("common", {})
    juso_list = results.get("juso", [])

    if common.get("errorCode") != "0":
        return build_result(
            status="query_failed",
            error_code=common.get("errorCode"),
            error_message=common.get("errorMessage"),
            debug={"raw_common": common},
        )

    if not juso_list:
        return build_result(
            status="not_found",
            error_code="DETAIL_NOT_FOUND",
            error_message="상세주소 검색 결과가 없습니다.",
            debug={"raw_common": common},
        )

    items = []
    for item in juso_list:
        items.append({
            "dongNm": normalize_text(item.get("dongNm")),
            "floorNm": normalize_text(item.get("floorNm")),
            "hoNm": normalize_text(item.get("hoNm")),
        })

    return build_result(
        status="success",
        data={
            "detail_count": len(items),
            "items": items,
        },
        debug={
            "totalCount": common.get("totalCount"),
        },
    )


def match_detail_items(
    items: list[dict],
    target_dong: str | None,
    target_floor: str | None,
    target_ho: str | None,
) -> dict:
    matched_items = []

    for item in items:
        ok = True

        if target_dong and normalize_text(item.get("dongNm")) != normalize_text(target_dong):
            ok = False

        if target_floor and normalize_text(item.get("floorNm")) != normalize_text(target_floor):
            ok = False

        if target_ho and normalize_text(item.get("hoNm")) != normalize_text(target_ho):
            ok = False

        if ok:
            matched_items.append(item)

    return {
        "matched_count": len(matched_items),
        "matched_items": matched_items[:20],
    }


def verify_address(base_address: str, leased_part: str) -> dict:
    leased_info = parse_leased_part(leased_part)

    try:
        road_raw = search_road_address(base_address)
    except requests.RequestException as e:
        return build_result(
            status="query_failed",
            error_code="ROAD_HTTP_FAILED",
            error_message=str(e),
            debug={"base_address": base_address, "leased_part": leased_part},
        )
    except ValueError as e:
        return build_result(
            status="query_failed",
            error_code="ROAD_JSON_PARSE_FAILED",
            error_message=str(e),
            debug={"base_address": base_address, "leased_part": leased_part},
        )

    road_parsed = parse_road_result(road_raw)
    if road_parsed["status"] != "success":
        road_parsed["debug"].update({
            "base_address": base_address,
            "leased_part": leased_part,
            "leased_info": leased_info,
            "verification_stage": "road",
        })
        return road_parsed

    road_data = road_parsed["data"]

    if not leased_info["dong"] and not leased_info["floor"] and not leased_info["ho"]:
        return build_result(
            status="success",
            data={
                "input": {
                    "base_address": base_address,
                    "leased_part": leased_part,
                },
                "road": road_data,
                "leased_info": leased_info,
                "detail_available": False,
                "detail_match": None,
            },
            debug={
                "road_debug": road_parsed.get("debug", {}),
                "detail_skipped": True,
            },
        )

    dong_nm = leased_info["dong"] or ""

    try:
        detail_raw = search_detail_address(
            adm_cd=road_data["admCd"],
            rn_mgt_sn=road_data["rnMgtSn"],
            udrt_yn=road_data["udrtYn"],
            buld_mnnm=road_data["buldMnnm"],
            buld_slno=road_data["buldSlno"],
            dong_nm=dong_nm,
            search_type="floorho",
        )
    except requests.RequestException as e:
        return build_result(
            status="query_failed",
            error_code="DETAIL_HTTP_FAILED",
            error_message=str(e),
            debug={
                "base_address": base_address,
                "leased_part": leased_part,
                "leased_info": leased_info,
                "road_data": road_data,
                "verification_stage": "detail",
            },
        )
    except ValueError as e:
        return build_result(
            status="query_failed",
            error_code="DETAIL_JSON_PARSE_FAILED",
            error_message=str(e),
            debug={
                "base_address": base_address,
                "leased_part": leased_part,
                "leased_info": leased_info,
                "road_data": road_data,
                "verification_stage": "detail",
            },
        )

    detail_parsed = parse_detail_result(detail_raw)

    if detail_parsed["status"] == "not_found":
        return build_result(
            status="partial_match",
            data={
                "input": {
                    "base_address": base_address,
                    "leased_part": leased_part,
                },
                "road": road_data,
                "leased_info": leased_info,
                "detail_available": False,
                "detail_match": False,
            },
            error_message="기본주소는 존재하지만 상세주소 목록을 확인하지 못했습니다.",
            debug={
                "verification_stage": "detail",
                "road_debug": road_parsed.get("debug", {}),
                "detail_debug": detail_parsed.get("debug", {}),
            },
        )

    if detail_parsed["status"] != "success":
        return build_result(
            status="query_failed",
            error_code=detail_parsed.get("error_code"),
            error_message=detail_parsed.get("error_message"),
            debug={
                "base_address": base_address,
                "leased_part": leased_part,
                "leased_info": leased_info,
                "road_data": road_data,
                "detail_debug": detail_parsed.get("debug", {}),
            },
        )

    detail_data = detail_parsed["data"]
    items = detail_data["items"]

    match_result = match_detail_items(
        items=items,
        target_dong=leased_info["dong"],
        target_floor=leased_info["floor"],
        target_ho=leased_info["ho"],
    )

    if match_result["matched_count"] > 0:
        return build_result(
            status="success",
            data={
                "input": {
                    "base_address": base_address,
                    "leased_part": leased_part,
                },
                "road": road_data,
                "leased_info": leased_info,
                "detail_available": True,
                "detail_match": True,
                "matched_count": match_result["matched_count"],
                "matched_items": match_result["matched_items"],
                "detail_count": detail_data["detail_count"],
            },
            debug={
                "road_debug": road_parsed.get("debug", {}),
                "detail_debug": detail_parsed.get("debug", {}),
            },
        )

    return build_result(
        status="not_found",
        data={
            "input": {
                "base_address": base_address,
                "leased_part": leased_part,
            },
            "road": road_data,
            "leased_info": leased_info,
            "detail_available": True,
            "detail_match": False,
            "detail_count": detail_data["detail_count"],
        },
        error_code="DETAIL_VALUE_NOT_FOUND",
        error_message="기본주소는 존재하지만 입력한 동/층/호와 일치하는 상세주소를 찾지 못했습니다.",
        debug={
            "road_debug": road_parsed.get("debug", {}),
            "detail_debug": detail_parsed.get("debug", {}),
            "sample_items": items[:20],
        },
    )


if __name__ == "__main__":
    result = verify_address(
        base_address="서울특별시 강서구 양천로63길 38",
        leased_part="104동 1702호 전부",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

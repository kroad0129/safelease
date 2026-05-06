import hashlib
import json
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import psycopg
from openai import OpenAI

from app.core.common import load_project_env, save_json
from app.services.rag_contract_rules import RAG_CONDITION_FIELD_PATHS, normalize_review_level


DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_ANALYSIS_MODEL = "gpt-5.4-mini"
LEGAL_FETCH_K = 12
GUIDE_FETCH_K = 12
CLAUSE_FETCH_K = 8
LEGAL_MIN_SIMILARITY = 0.4
GUIDE_MIN_SIMILARITY = 0.4
CLAUSE_MIN_SIMILARITY = 0.4

SYSTEM_INSTRUCTIONS = """
너는 주택 임대차 계약서를 분석하는 한국어 법률/실무 보조 시스템이다.
입력에는 계약서 구조화 결과와, 각 계약조건/특약에 대해 검색된 법령 근거/안내자료/유사 특약이 함께 주어진다.

반드시 지켜야 할 원칙:
1. 법령 위반 또는 무효라고 단정할 때는 legal_evidence를 우선 근거로 사용한다.
2. guidance_evidence만으로는 '주의 필요', '분쟁 소지', '실무상 점검 필요' 수준으로 표현한다.
3. 특약 분석 시 임차인 관점에서 유리/불리/중립을 판단하되, 이유를 짧고 명확하게 설명한다.
4. 계약조건 분석 시 누락, 모호성, 비정상적 수치, 기간 오류 가능성을 설명한다.
5. 답변에는 가능한 경우 관련 법령명과 조문번호를 함께 적는다.
6. 근거가 약하면 확실하지 않다고 명시한다.
7. 월 차임 금액이나 차임 지급 방식이 통상적으로 기재된 경우에는, 보증금 일부를 월세로 전환했다는 명시적 근거가 없으면 전월세전환율만을 이유로 '주의' 처리하지 않는다.

출력 목표:
- 계약조건별 요약 판단
- 특약별 유리/불리/주의 판단
- 핵심 법령 근거
- 실무상 주의점
- 필요하면 더 나은 특약 문구 제안
""".strip()

ANALYSIS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "contract_conditions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "judgment": {"type": "string"},
                    "review_level": {"type": "string", "enum": ["양호", "보통", "주의"]},
                    "reason": {"type": "string"},
                    "legal_basis": {"type": "array", "items": {"type": "string"}},
                    "practical_notes": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["label", "judgment", "review_level", "reason", "legal_basis", "practical_notes"],
                "additionalProperties": False,
            },
        },
        "special_terms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "order": {"type": "integer"},
                    "label": {"type": "string"},
                    "judgment": {"type": "string"},
                    "review_level": {"type": "string", "enum": ["양호", "보통", "주의"]},
                    "reason": {"type": "string"},
                    "legal_basis": {"type": "array", "items": {"type": "string"}},
                    "practical_notes": {"type": "array", "items": {"type": "string"}},
                    "suggested_revision": {"type": ["string", "null"]},
                },
                "required": [
                    "order",
                    "label",
                    "judgment",
                    "review_level",
                    "reason",
                    "legal_basis",
                    "practical_notes",
                    "suggested_revision",
                ],
                "additionalProperties": False,
            },
        },
        "overall_summary": {
            "type": "object",
            "properties": {
                "key_risks": {"type": "array", "items": {"type": "string"}},
                "key_strengths": {"type": "array", "items": {"type": "string"}},
                "recommended_next_actions": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["key_risks", "key_strengths", "recommended_next_actions"],
            "additionalProperties": False,
        },
    },
    "required": ["contract_conditions", "special_terms", "overall_summary"],
    "additionalProperties": False,
}

LEGAL_BASIS_VERIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "contract_conditions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "legal_basis_reviews": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "basis": {"type": "string"},
                                "title": {"type": "string"},
                                "relevance": {"type": "string", "enum": ["direct", "supporting", "irrelevant"]},
                                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                                "why_relevant": {"type": "string"},
                            },
                            "required": ["basis", "title", "relevance", "confidence", "why_relevant"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["label", "legal_basis_reviews"],
                "additionalProperties": False,
            },
        },
        "special_terms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "order": {"type": "integer"},
                    "label": {"type": "string"},
                    "legal_basis_reviews": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "basis": {"type": "string"},
                                "title": {"type": "string"},
                                "relevance": {"type": "string", "enum": ["direct", "supporting", "irrelevant"]},
                                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                                "why_relevant": {"type": "string"},
                            },
                            "required": ["basis", "title", "relevance", "confidence", "why_relevant"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["order", "label", "legal_basis_reviews"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["contract_conditions", "special_terms"],
    "additionalProperties": False,
}

def json_default(value: Any) -> Any:
    try:
        import decimal

        if isinstance(value, decimal.Decimal):
            return float(value)
    except Exception:
        pass
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def load_runtime_env() -> None:
    load_project_env()


def get_openai_client() -> OpenAI:
    load_runtime_env()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY가 없습니다.")
    return OpenAI(api_key=api_key)


def get_connection_string() -> str:
    load_runtime_env()
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5433")
    dbname = os.getenv("POSTGRES_DB", "rent")
    user = os.getenv("POSTGRES_USER", "rent")
    password = os.getenv("POSTGRES_PASSWORD", "rent1234")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


def money_value(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        normalized = re.sub(r"[^\d.-]", "", value)
        if not normalized:
            return None
        try:
            return Decimal(normalized)
        except InvalidOperation:
            return None
    return None


def format_money(value: Decimal | int | float | str | None) -> str:
    amount = money_value(value)
    if amount is None:
        return "미확인"
    if amount == amount.to_integral_value():
        return f"{int(amount):,}원"
    return f"{amount:,.2f}원"


def has_meaningful_money_text(raw_text: Any) -> bool:
    if raw_text is None:
        return False
    text = str(raw_text).strip()
    if not text:
        return False
    if text in {"없음", "해당 없음", "해당없음", "무", "0", "0원"}:
        return False

    compact = re.sub(r"\s+", "", text)
    placeholder_removed = re.sub(r"[금원정₩\\,()\[\]{}._\-:：]", "", compact)
    if not placeholder_removed:
        return False
    if placeholder_removed in {"없음", "해당없음", "무"}:
        return False
    return True


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def infer_topic(text: str) -> str:
    rules = [
        ("deposit_return", ["보증금 반환", "반환 지연", "동시이행", "명도 전 반환", "퇴거 전 반환"]),
        ("priority_protection", ["확정일자", "전입", "대항력", "우선변제", "최우선변제", "선순위"]),
        ("rent_increase", ["차임 증감", "증액", "월세 인상", "전환율"]),
        ("renewal", ["갱신", "계약갱신", "묵시적 갱신", "갱신거절"]),
        ("broker_duty", ["중개대상물", "확인설명", "공인중개사", "중개보수"]),
        ("management_fee", ["관리비", "공용관리비", "사용료"]),
        ("access_and_privacy", ["출입", "임대인 출입", "무단 출입", "집보기", "사생활"]),
        ("insurance_and_guarantee", ["보증보험", "반환보증", "보증금 보호"]),
        ("sale_and_transfer", ["매도", "매매", "소유권 이전", "임대인 지위 승계"]),
        ("option_and_fixture", ["옵션", "냉장고", "세탁기", "에어컨", "붙박이"]),
        ("pet", ["반려동물", "애완동물"]),
        ("move_in_and_possession", ["인도 지연", "열쇠", "입주 지연", "출입 권한"]),
        ("restoration", ["원상복구", "원상회복", "자연마모", "통상 손모", "청소비"]),
        ("deposit_protection", ["보증금", "전입", "담보권", "권리관계"]),
        ("repair_and_defect", ["하자", "누수", "보일러", "도배", "수리", "보수"]),
        ("registry_and_rights", ["등기부", "권리관계", "말소", "근저당"]),
        ("identity_and_authority", ["임대인", "대리", "소유자", "중개"]),
        ("contract_basics", ["계약기간", "잔금", "계약금", "중도금", "차임"]),
        ("special_clause", ["특약", "해지", "해제"]),
        ("broker_and_fee", ["중개", "중개수수료"]),
        ("sublease_and_transfer", ["전대", "양도"]),
    ]
    for topic, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return topic
    return "general_guidance"


def infer_topic_from_query(label: str, query_text: str, query_type: str) -> str:
    joined = f"{label} {query_text}"
    if query_type == "special_term":
        return infer_topic(joined)

    rules = [
        ("deposit_return", ["보증금 반환", "반환 지연", "동시이행", "명도 전 반환", "퇴거 전 반환"]),
        ("priority_protection", ["확정일자", "전입", "대항력", "우선변제", "최우선변제", "선순위", "담보권"]),
        ("renewal", ["갱신", "계약갱신", "묵시적 갱신", "갱신거절"]),
        ("rent_increase", ["차임 증감", "증액", "월세 인상", "전환율"]),
        ("broker_duty", ["광고", "설명서", "중개", "공인중개사", "중개보수"]),
        ("management_fee", ["관리비", "공용관리비", "사용료"]),
        ("access_and_privacy", ["출입", "임대인 출입", "무단 출입", "집보기", "사생활"]),
        ("insurance_and_guarantee", ["보증보험", "반환보증", "보증금 보호"]),
        ("sale_and_transfer", ["매도", "매매", "소유권 이전", "임대인 지위 승계"]),
        ("option_and_fixture", ["옵션", "냉장고", "세탁기", "에어컨", "붙박이"]),
        ("pet", ["반려동물", "애완동물"]),
        ("move_in_and_possession", ["인도 지연", "열쇠", "입주 지연", "출입 권한"]),
        ("restoration", ["원상복구", "원상회복", "자연마모", "통상 손모", "청소비"]),
        ("deposit_protection", ["보증금", "전입", "담보권"]),
        ("lease_period", ["기간", "존속기간", "인도일", "종료일", "입주일"]),
        ("payment_schedule", ["월 차임", "차임", "지급", "선불", "후불", "매월"]),
        ("payment_structure", ["계약금", "중도금", "잔금", "보증금 합계", "금액 구조"]),
        ("property_spec", ["목적물", "주소", "동", "호", "면적"]),
        ("identity_and_authority", ["광고", "설명서", "중개", "대리", "소유자"]),
        ("repair_and_defect", ["하자", "누수", "보일러", "도배", "수리", "보수"]),
    ]
    for topic, keywords in rules:
        if any(keyword in joined for keyword in keywords):
            return topic
    return "contract_basics"


def build_preferred_legal_refs(label: str, query_text: str, topic: str) -> list[tuple[str, int | None]]:
    joined = f"{label} {query_text}"
    refs: list[tuple[str, int | None]] = []

    if any(keyword in joined for keyword in ["차임", "월 차임", "월세", "지급 방식"]):
        refs.extend([("민법", 633), ("주택임대차보호법", 7), ("주택임대차보호법", 10)])
    if any(keyword in joined for keyword in ["보증금", "잔금", "계약금", "중도금"]):
        refs.extend([("주택임대차보호법", 10), ("민법", 565), ("주택임대차보호법", 13)])
    if any(keyword in joined for keyword in ["기간", "존속기간", "인도일", "종료일"]):
        refs.extend([("민법", 623), ("주택임대차보호법", 4)])
    if any(keyword in joined for keyword in ["목적물", "주소", "동", "호"]):
        refs.extend([("주택임대차보호법", 2), ("민법", 623)])
    if any(keyword in joined for keyword in ["하자", "수리", "보수", "누수", "도배", "보일러"]):
        refs.extend([("민법", 623), ("민법", 634), ("주택임대차보호법", 10)])
    if any(keyword in joined for keyword in ["광고", "설명서", "중개"]):
        refs.extend([("공인중개사법", 25), ("공인중개사법 시행규칙", 16)])
    if any(keyword in joined for keyword in ["전입", "확정일자", "선순위", "담보권", "보증금 반환", "인도"]):
        refs.extend([("주택임대차보호법", 3), ("주택임대차보호법", 10), ("주택임대차보호법", 13)])

    deduped: list[tuple[str, int | None]] = []
    seen: set[tuple[str, int | None]] = set()
    for item in refs:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def tokenize_korean_text(text: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^0-9A-Za-z가-힣]+", text or "")
        if len(token) >= 2
    }


def to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def score_match(
    query_text: str,
    topic: str,
    match: dict[str, Any],
    preferred_refs: list[tuple[str, int | None]] | None = None,
    law_only: bool = False,
) -> float:
    similarity = to_float(match.get("similarity"))
    match_topic = match.get("topic")
    source_type = match.get("source_type")
    match_text = match.get("chunk_text") or match.get("raw_text") or ""
    overlap = len(tokenize_korean_text(query_text) & tokenize_korean_text(match_text))

    score = similarity
    if match_topic == topic:
        score += 0.08
    elif match_topic == "general_guidance":
        score += 0.02

    if law_only and match.get("is_primary_authority"):
        score += 0.04
    if source_type == "law":
        score += 0.02
    score += min(overlap, 4) * 0.015

    law_name = str(match.get("law_name") or match.get("source_name") or "")
    article_no = match.get("article_no")
    if preferred_refs:
        for preferred_law, preferred_article in preferred_refs:
            if law_name == preferred_law and (preferred_article is None or article_no == preferred_article):
                score += 0.16
                break

    title = str(match.get("title") or "")
    if title.endswith("제543조") or match_text.strip() == "제3관 계약의 해지, 해제":
        score -= 0.12
    if len(match_text.strip()) < 20:
        score -= 0.08
    return score


def rerank_chunk_matches(
    query_text: str,
    topic: str,
    matches: list[dict[str, Any]],
    limit: int,
    min_similarity: float,
    preferred_refs: list[tuple[str, int | None]] | None,
    law_only: bool,
) -> list[dict[str, Any]]:
    ranked = []
    for match in matches:
        similarity = to_float(match.get("similarity"))
        if similarity < min_similarity:
            continue
        ranked.append((score_match(query_text, topic, match, preferred_refs=preferred_refs, law_only=law_only), similarity, match))

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    results = []
    seen_ids: set[str] = set()
    for _score, _similarity, match in ranked:
        key = str(match.get("chunk_id"))
        if key in seen_ids:
            continue
        seen_ids.add(key)
        results.append(match)
        if len(results) >= limit:
            break
    return results


def rerank_clause_matches(
    query_text: str,
    topic: str,
    matches: list[dict[str, Any]],
    limit: int,
    min_similarity: float,
) -> list[dict[str, Any]]:
    ranked = []
    for match in matches:
        similarity = to_float(match.get("similarity"))
        if similarity < min_similarity:
            continue
        overlap = len(tokenize_korean_text(query_text) & tokenize_korean_text(match.get("raw_text") or ""))
        score = similarity + min(overlap, 4) * 0.02
        if match.get("topic") == topic:
            score += 0.08
        elif match.get("topic") == "special_clause":
            score += 0.03
        if match.get("favorability") == "favorable":
            score += 0.02
        ranked.append((score, similarity, match))

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    results = []
    seen_ids: set[str] = set()
    for _score, _similarity, match in ranked:
        key = str(match.get("library_clause_id"))
        if key in seen_ids:
            continue
        seen_ids.add(key)
        results.append(match)
        if len(results) >= limit:
            break
    return results


def build_search_topics(topic: str, source_kind: str) -> list[str]:
    fallback_map = {
        "payment_structure": ["contract_basics", "general_guidance"],
        "payment_schedule": ["contract_basics", "deposit_protection", "general_guidance"],
        "lease_period": ["contract_basics", "general_guidance"],
        "property_spec": ["contract_basics", "general_guidance"],
        "repair_and_defect": ["repair_and_defect", "special_clause", "general_guidance"],
        "identity_and_authority": ["identity_and_authority", "general_guidance"],
        "deposit_protection": ["deposit_protection", "general_guidance"],
        "deposit_return": ["deposit_protection", "contract_basics", "general_guidance"],
        "priority_protection": ["deposit_protection", "registry_and_rights", "general_guidance"],
        "renewal": ["lease_period", "contract_basics", "general_guidance"],
        "rent_increase": ["payment_schedule", "contract_basics", "general_guidance"],
        "broker_duty": ["identity_and_authority", "broker_and_fee", "general_guidance"],
        "management_fee": ["payment_schedule", "contract_basics", "general_guidance"],
        "tax_and_arrears": ["deposit_protection", "registry_and_rights", "general_guidance"],
        "early_termination": ["contract_basics", "special_clause", "general_guidance"],
        "sublease_and_transfer": ["special_clause", "general_guidance"],
        "restoration": ["repair_and_defect", "special_clause", "general_guidance"],
        "restoration_and_damage": ["repair_and_defect", "special_clause", "general_guidance"],
        "access_and_privacy": ["special_clause", "general_guidance"],
        "insurance_and_guarantee": ["deposit_protection", "special_clause", "general_guidance"],
        "sale_and_transfer": ["deposit_protection", "registry_and_rights", "special_clause", "general_guidance"],
        "option_and_fixture": ["repair_and_defect", "special_clause", "general_guidance"],
        "pet": ["special_clause", "general_guidance"],
        "move_in_and_possession": ["lease_period", "contract_basics", "general_guidance"],
    }

    topics = [topic]
    topics.extend(fallback_map.get(topic, ["general_guidance"]))
    if source_kind == "clause" and "special_clause" not in topics:
        topics.append("special_clause")

    deduped = []
    seen: set[str] = set()
    for item in topics:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def find_contract_term(
    contract: dict[str, Any],
    article_no: str | None = None,
    keywords: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    terms = [term for term in contract.get("contract_terms", []) if isinstance(term, dict)]
    if article_no:
        for term in terms:
            if term.get("article_no") == article_no:
                return term

    for term in terms:
        haystack = " ".join(str(term.get(key) or "") for key in ("article_no", "title", "content"))
        if all(keyword in haystack for keyword in keywords):
            return term
    return None


def build_diagnostics(contract: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    payment = contract.get("payment") or {}

    if contract.get("lease_type") is None:
        diagnostics.append(
            {
                "query_type": "contract_condition",
                "label": "전세/월세 유형 확인",
                "query_text": "문서 상단의 전세/월세 체크 표시가 불명확해 계약 유형을 문서상으로 확정하기 어렵습니다. 보증금과 차임 구조상 월세 계약으로 보이더라도 체크 표시를 다시 확인해야 합니다.",
                "topic": "payment_schedule",
                "severity": "medium",
            }
        )

    deposit = money_value((payment.get("deposit") or {}).get("normalized_value"))
    balance = money_value((payment.get("balance") or {}).get("normalized_value"))
    contract_money = money_value((payment.get("contract_money") or {}).get("normalized_value"))
    intermediate_money = money_value((payment.get("intermediate_money") or {}).get("normalized_value"))
    if deposit is not None and balance is not None and balance > deposit:
        diagnostics.append(
            {
                "query_type": "contract_condition",
                "label": "잔금 구조 확인",
                "query_text": f"보증금은 {format_money(deposit)}인데 잔금이 {format_money(balance)}으로 더 크게 기재되어 있습니다.",
                "topic": "payment_structure",
                "severity": "high",
            }
        )
    payment_parts = [amount for amount in [contract_money, intermediate_money, balance] if amount is not None]
    has_upfront_payment = contract_money is not None or intermediate_money is not None
    if deposit is not None and has_upfront_payment and balance is not None and sum(payment_parts, Decimal(0)) != deposit:
        sum_text_parts: list[str] = []
        if contract_money is not None:
            sum_text_parts.append(f"계약금은 {format_money(contract_money)}")
        if intermediate_money is not None:
            sum_text_parts.append(f"중도금은 {format_money(intermediate_money)}")
        if balance is not None:
            sum_text_parts.append(f"잔금은 {format_money(balance)}")
        diagnostics.append(
            {
                "query_type": "contract_condition",
                "label": "보증금 합계 확인",
                "query_text": ", ".join(sum_text_parts) + f", 보증금은 {format_money(deposit)}입니다.",
                "topic": "payment_structure",
                "severity": "high",
            }
        )

    contract_term = find_contract_term(contract, article_no="제2조", keywords=("인도", "종료"))
    if contract_term:
        dates = contract_term.get("dates") or []
        if len(dates) >= 2:
            handover = dates[0].get("normalized_value")
            expiry = dates[1].get("normalized_value")
            if handover and expiry and expiry < handover:
                diagnostics.append(
                    {
                        "query_type": "contract_condition",
                        "label": "임대차 기간 확인",
                        "query_text": f"인도일은 {handover}인데 종료일이 {expiry}로 더 빠르게 기재되어 있습니다.",
                        "topic": "lease_period",
                        "severity": "high",
                    }
                )

    intermediate_money_field = payment.get("intermediate_money") or {}
    if (
        has_meaningful_money_text(intermediate_money_field.get("raw_text"))
        and intermediate_money_field.get("normalized_value") is None
    ):
        diagnostics.append(
            {
                "query_type": "contract_condition",
                "label": "중도금 기재 확인",
                "query_text": "중도금 칸에 원문 흔적은 있지만 정규화된 금액이 없습니다.",
                "topic": "payment_structure",
                "severity": "low",
            }
        )

    return diagnostics


def build_contract_condition_queries(contract: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    payment = contract.get("payment") or {}

    deposit = money_value((payment.get("deposit") or {}).get("normalized_value"))
    monthly_rent = money_value((payment.get("monthly_rent") or {}).get("normalized_value"))
    balance = money_value((payment.get("balance") or {}).get("normalized_value"))
    due_day = (payment.get("monthly_due_day") or {}).get("normalized_value")
    payment_type = (payment.get("rent_payment_type") or {}).get("value")

    if deposit is not None:
        items.append(
            {
                "query_type": "contract_condition",
                "label": "보증금 조건",
                "query_text": f"이 계약의 보증금은 {format_money(deposit)}입니다.",
                "topic": "payment_structure",
                "severity": "medium",
            }
        )
    if balance is not None:
        items.append(
            {
                "query_type": "contract_condition",
                "label": "잔금 조건",
                "query_text": f"이 계약의 잔금은 {format_money(balance)}입니다.",
                "topic": "payment_structure",
                "severity": "medium",
            }
        )
    if monthly_rent is not None:
        items.append(
            {
                "query_type": "contract_condition",
                "label": "월 차임 조건",
                "query_text": f"이 계약의 월 차임은 {format_money(monthly_rent)}입니다.",
                "topic": "payment_schedule",
                "severity": "medium",
            }
        )
    if payment_type or due_day is not None:
        payment_schedule_bits: list[str] = []
        if payment_type:
            payment_schedule_bits.append(f"{payment_type} 지급")
        if due_day is not None:
            payment_schedule_bits.append(f"매월 {due_day}일 지급")
        items.append(
            {
                "query_type": "contract_condition",
                "label": "차임 지급 방식",
                "query_text": "이 계약의 차임 지급 방식은 " + ", ".join(payment_schedule_bits) + "입니다.",
                "topic": "payment_schedule",
                "severity": "medium",
            }
        )

    contract_term = find_contract_term(contract, article_no="제2조", keywords=("인도", "종료"))
    if contract_term and contract_term.get("content"):
        items.append(
            {
                "query_type": "contract_condition",
                "label": "임대차 기간 조건",
                "query_text": contract_term.get("content") or "",
                "topic": "lease_period",
                "severity": "medium",
            }
        )

    leased_part = (((contract.get("property") or {}).get("leased_part") or {}).get("raw_text"))
    property_address = (((contract.get("property") or {}).get("address") or {}).get("value"))
    if leased_part or property_address:
        text_parts = []
        if property_address:
            text_parts.append(f"목적물 주소는 {property_address}")
        if leased_part:
            text_parts.append(f"임대할 부분은 {leased_part}")
        items.append(
            {
                "query_type": "contract_condition",
                "label": "목적물 표시",
                "query_text": ". ".join(text_parts) + "입니다.",
                "topic": "property_spec",
                "severity": "low",
            }
        )

    return items


def build_query_items(contract: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    items.extend(build_contract_condition_queries(contract))
    items.extend(build_diagnostics(contract))

    for term in contract.get("special_terms", []) or []:
        content = (term.get("content") or "").strip()
        if not content:
            continue
        items.append(
            {
                "query_type": "special_term",
                "label": f"특약 {term.get('order')}",
                "query_text": content,
                "topic": infer_topic_from_query(f"특약 {term.get('order')}", content, "special_term"),
                "severity": "medium",
                "order": term.get("order"),
            }
        )

    unique_items: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for item in items:
        key = (item.get("label") or "", item.get("query_text") or "")
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique_items.append(item)
    return unique_items


def embed_texts(client: OpenAI, model: str, texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in response.data]


def fetch_chunk_matches(
    conn: psycopg.Connection[Any],
    embedding_model: str,
    query_vector: list[float],
    topics: list[str],
    limit: int,
    law_only: bool,
) -> list[dict[str, Any]]:
    sql = """
    select
        sc.chunk_id,
        sc.source_type,
        sc.source_name,
        sc.title,
        sc.chunk_text,
        sc.topic,
        sc.subtopic,
        sc.law_name,
        sc.article_no,
        sc.article_branch_no,
        sc.is_primary_authority,
        round(cast((1 - (sce.embedding <=> %(embedding)s::vector)) as numeric), 6) as similarity
    from source_chunk_embeddings sce
    join source_chunks sc on sc.chunk_id = sce.chunk_id
    where sce.embedding_model = %(embedding_model)s
      and (%(law_only)s = false or sc.is_primary_authority = true)
      and (sc.topic = any(%(topics)s) or sc.topic = 'general_guidance')
    order by sce.embedding <=> %(embedding)s::vector
    limit %(limit)s
    """
    params = {
        "embedding_model": embedding_model,
        "embedding": vector_literal(query_vector),
        "topics": topics,
        "limit": limit,
        "law_only": law_only,
    }
    with conn.cursor() as cur:
        cur.execute(sql, params)
        columns = [desc.name for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def fetch_clause_matches(
    conn: psycopg.Connection[Any],
    embedding_model: str,
    query_vector: list[float],
    topics: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    sql = """
    select
        cl.library_clause_id,
        cl.source_name,
        cl.title,
        cl.raw_text,
        cl.topic,
        cl.perspective,
        cl.favorability,
        cl.risk_level,
        cl.legality_status,
        round(cast((1 - (cle.embedding <=> %(embedding)s::vector)) as numeric), 6) as similarity
    from clause_library_embeddings cle
    join clause_library cl on cl.library_clause_id = cle.library_clause_id
    where cle.embedding_model = %(embedding_model)s
      and (cl.topic = any(%(topics)s) or cl.topic = 'special_clause')
    order by cle.embedding <=> %(embedding)s::vector
    limit %(limit)s
    """
    params = {
        "embedding_model": embedding_model,
        "embedding": vector_literal(query_vector),
        "topics": topics,
        "limit": limit,
    }
    with conn.cursor() as cur:
        cur.execute(sql, params)
        columns = [desc.name for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def build_contract_snapshot(contract: dict[str, Any]) -> dict[str, Any]:
    payment = contract.get("payment") or {}
    property_info = contract.get("property") or {}
    return {
        "document_type": contract.get("document_type"),
        "lease_type": contract.get("lease_type"),
        "property": {
            "address": ((property_info.get("address") or {}).get("value")),
            "leased_part": ((property_info.get("leased_part") or {}).get("raw_text")),
            "building_area_m2": (((property_info.get("building") or {}).get("area_m2") or {}).get("normalized_value")),
        },
        "payment": {
            "deposit": (payment.get("deposit") or {}).get("normalized_value"),
            "contract_money": (payment.get("contract_money") or {}).get("normalized_value"),
            "intermediate_money": (payment.get("intermediate_money") or {}).get("normalized_value"),
            "balance": (payment.get("balance") or {}).get("normalized_value"),
            "monthly_rent": (payment.get("monthly_rent") or {}).get("normalized_value"),
            "rent_payment_type": (payment.get("rent_payment_type") or {}).get("value"),
            "monthly_due_day": (payment.get("monthly_due_day") or {}).get("normalized_value"),
        },
        "parties": {
            "lessor_name": ((contract.get("lessor") or {}).get("name") or {}).get("value"),
            "lessee_name": ((contract.get("lessee") or {}).get("name") or {}).get("value"),
            "broker_office_name": ((contract.get("broker") or {}).get("office_name") or {}).get("value"),
        },
    }


def compress_legal_matches(matches: list[dict[str, Any]], top_k: int = 3) -> list[dict[str, Any]]:
    return [
        {
            "title": match.get("title"),
            "law_name": match.get("law_name"),
            "article_no": match.get("article_no"),
            "article_branch_no": match.get("article_branch_no"),
            "chunk_text": match.get("chunk_text"),
            "similarity": match.get("similarity"),
        }
        for match in matches[:top_k]
    ]


def compress_guidance_matches(matches: list[dict[str, Any]], top_k: int = 3) -> list[dict[str, Any]]:
    rows = []
    seen_chunk_ids: set[str] = set()
    for match in matches:
        chunk_id = match.get("chunk_id")
        if chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk_id)
        rows.append(
            {
                "source_name": match.get("source_name"),
                "title": match.get("title"),
                "subtopic": match.get("subtopic"),
                "chunk_text": match.get("chunk_text"),
                "related_law_name": match.get("law_name"),
                "related_article_no": match.get("article_no"),
                "similarity": match.get("similarity"),
            }
        )
        if len(rows) >= top_k:
            break
    return rows


def compress_clause_matches(matches: list[dict[str, Any]], top_k: int = 2) -> list[dict[str, Any]]:
    return [
        {
            "title": match.get("title"),
            "raw_text": match.get("raw_text"),
            "favorability": match.get("favorability"),
            "risk_level": match.get("risk_level"),
            "legality_status": match.get("legality_status"),
            "similarity": match.get("similarity"),
        }
        for match in matches[:top_k]
    ]


def build_analysis_items(rag_result: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for query in rag_result.get("queries", []):
        item_type = "special_term" if query.get("query_type") == "special_term" else "contract_condition"
        items.append(
            {
                "item_type": item_type,
                "label": query.get("label"),
                "field_path": RAG_CONDITION_FIELD_PATHS.get(query.get("label") or ""),
                "topic": query.get("topic"),
                "severity": query.get("severity"),
                "query_text": query.get("query_text"),
                "special_term_order": query.get("order"),
                "legal_evidence": compress_legal_matches(query.get("legal_matches", [])),
                "guidance_evidence": compress_guidance_matches(query.get("guide_matches", [])),
                "similar_clause_examples": compress_clause_matches(query.get("clause_matches", [])),
            }
        )
    return items


def build_output_schema_hint() -> dict[str, Any]:
    return {
        "contract_conditions": [
            {
                "label": "보증금·차임 조건",
                "judgment": "확인 필요 | 무난함 | 주의 필요",
                "review_level": "양호 | 보통 | 주의",
                "reason": "짧은 설명",
                "legal_basis": ["법령명 제n조"],
                "practical_notes": ["실무상 점검 포인트"],
            }
        ],
        "special_terms": [
            {
                "order": 1,
                "label": "특약 1",
                "judgment": "임차인에게 유리 | 중립 | 임차인에게 불리 | 주의 필요",
                "review_level": "양호 | 보통 | 주의",
                "reason": "짧은 설명",
                "legal_basis": ["법령명 제n조"],
                "practical_notes": ["실무상 점검 포인트"],
                "suggested_revision": "필요할 때만 제안 문구",
            }
        ],
        "overall_summary": {
            "key_risks": ["핵심 위험"],
            "key_strengths": ["핵심 장점"],
            "recommended_next_actions": ["다음 확인 사항"],
        },
    }


def build_llm_payload(contract: dict[str, Any], rag_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": "analyze_real_estate_lease_contract_conditions_and_special_terms",
        "system_instructions": SYSTEM_INSTRUCTIONS,
        "contract_snapshot": build_contract_snapshot(contract),
        "analysis_items": build_analysis_items(rag_result),
        "output_schema_hint": build_output_schema_hint(),
    }


def build_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": payload["system_instructions"],
        },
        {
            "role": "user",
            "content": (
                "아래 payload를 읽고 계약조건과 특약을 분석해줘. "
                "반드시 JSON만 출력하고, judgment는 간결한 한국어 표현으로 써줘. "
                "review_level은 양호, 보통, 주의 중 하나만 사용해줘. "
                "contract_conditions와 special_terms는 analysis_items 순서를 유지하고, "
                "label은 analysis_items.label 값을 글자 하나 바꾸지 말고 그대로 써줘.\n\n"
                + json.dumps(payload, ensure_ascii=False, indent=2, default=json_default)
            ),
        },
    ]


def run_rag_search(
    contract: dict[str, Any],
    client: OpenAI,
    embedding_model: str,
    legal_top_k: int = 5,
    guide_top_k: int = 5,
    clause_top_k: int = 3,
) -> dict[str, Any]:
    query_items = build_query_items(contract)
    if not query_items:
        raise ValueError("검색할 query item이 없습니다.")

    query_vectors = embed_texts(client, embedding_model, [item["query_text"] for item in query_items])
    conninfo = get_connection_string()

    results: list[dict[str, Any]] = []
    with psycopg.connect(conninfo) as conn:
        for item, vector in zip(query_items, query_vectors):
            topic = item.get("topic") or infer_topic_from_query(
                item.get("label") or "",
                item.get("query_text") or "",
                item.get("query_type") or "contract_condition",
            )
            item["topic"] = topic
            chunk_topics = build_search_topics(topic, "chunk")
            clause_topics = build_search_topics(topic, "clause")
            preferred_refs = build_preferred_legal_refs(item.get("label") or "", item.get("query_text") or "", topic)

            legal_candidates = fetch_chunk_matches(
                conn=conn,
                embedding_model=embedding_model,
                query_vector=vector,
                topics=chunk_topics,
                limit=max(legal_top_k, LEGAL_FETCH_K),
                law_only=True,
            )
            guide_candidates = fetch_chunk_matches(
                conn=conn,
                embedding_model=embedding_model,
                query_vector=vector,
                topics=chunk_topics,
                limit=max(guide_top_k, GUIDE_FETCH_K),
                law_only=False,
            )
            clause_candidates = fetch_clause_matches(
                conn=conn,
                embedding_model=embedding_model,
                query_vector=vector,
                topics=clause_topics,
                limit=max(clause_top_k, CLAUSE_FETCH_K),
            )
            legal_matches = rerank_chunk_matches(
                query_text=item["query_text"],
                topic=topic,
                matches=legal_candidates,
                limit=legal_top_k,
                min_similarity=LEGAL_MIN_SIMILARITY,
                preferred_refs=preferred_refs,
                law_only=True,
            )
            guide_matches = rerank_chunk_matches(
                query_text=item["query_text"],
                topic=topic,
                matches=guide_candidates,
                limit=guide_top_k,
                min_similarity=GUIDE_MIN_SIMILARITY,
                preferred_refs=preferred_refs,
                law_only=False,
            )
            clause_matches = rerank_clause_matches(
                query_text=item["query_text"],
                topic=topic,
                matches=clause_candidates,
                limit=clause_top_k,
                min_similarity=CLAUSE_MIN_SIMILARITY,
            )
            results.append(
                {
                    **item,
                    "query_hash": hashlib.sha256(item["query_text"].encode("utf-8")).hexdigest(),
                    "legal_matches": legal_matches,
                    "guide_matches": guide_matches,
                    "clause_matches": clause_matches,
                }
            )

    return {
        "embedding_model": embedding_model,
        "query_count": len(results),
        "queries": results,
    }


def generate_analysis_from_payload(
    payload: dict[str, Any],
    client: OpenAI,
    analysis_model: str,
) -> dict[str, Any]:
    response = client.responses.create(
        model=analysis_model,
        input=build_messages(payload),
        text={
            "format": {
                "type": "json_schema",
                "name": "contract_analysis_result",
                "schema": ANALYSIS_OUTPUT_SCHEMA,
                "strict": True,
            }
        },
    )
    return json.loads(response.output_text)


def normalize_analysis_labels(payload: dict[str, Any], analysis_result: dict[str, Any]) -> dict[str, Any]:
    condition_labels = [
        item.get("label")
        for item in payload.get("analysis_items", [])
        if item.get("item_type") == "contract_condition" and item.get("label")
    ]
    contract_conditions = analysis_result.get("contract_conditions")
    if isinstance(contract_conditions, list) and len(contract_conditions) == len(condition_labels):
        for item, label in zip(contract_conditions, condition_labels):
            if isinstance(item, dict):
                item["label"] = label
                item["review_level"] = normalize_review_level(item.get("review_level"), item.get("judgment"))

    special_term_labels_by_order = {
        item.get("special_term_order"): item.get("label")
        for item in payload.get("analysis_items", [])
        if item.get("item_type") == "special_term" and item.get("special_term_order") is not None and item.get("label")
    }
    for item in analysis_result.get("special_terms") or []:
        if not isinstance(item, dict):
            continue
        label = special_term_labels_by_order.get(item.get("order"))
        if label:
            item["label"] = label
        item["review_level"] = normalize_review_level(item.get("review_level"), item.get("judgment"))

    return analysis_result


def normalize_condition_judgments(analysis_result: dict[str, Any]) -> dict[str, Any]:
    for item in analysis_result.get("contract_conditions") or []:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        reason = item.get("reason") or ""
        if (
            label == "월 차임 조건"
            and item.get("review_level") == "주의"
            and "전환" in reason
            and (
                "보기 어렵" in reason
                or "문제 삼기 어렵" in reason
                or "단정할 수 없" in reason
                or not any(token in reason for token in ("초과", "상한", "위반", "과다", "불리"))
            )
        ):
            item["judgment"] = "무난함"
            item["review_level"] = "양호"
            item["reason"] = "월 차임 금액이 기재되어 있으며, 보증금 일부를 월세로 전환했다는 명시적 근거가 없으므로 금액 기재 자체는 통상 범위로 봅니다."
            practical_notes = item.get("practical_notes") or []
            item["practical_notes"] = [
                note
                for note in practical_notes
                if "전환" not in str(note) and "연체" not in str(note)
            ] or ["월 차임 지급일과 지급 계좌가 계약서에 명확히 적혀 있는지 확인하세요."]
    return analysis_result


def parse_legal_basis_ref(value: str) -> tuple[str, int, int | None] | None:
    match = re.search(r"(.+?)\s*제\s*(\d+)\s*조(?:의\s*(\d+))?", value or "")
    if not match:
        return None
    law_name = re.sub(r"\s+", "", match.group(1))
    article_no = int(match.group(2))
    article_branch_no = int(match.group(3)) if match.group(3) else None
    return law_name, article_no, article_branch_no


def format_legal_basis(law_name: str, article_no: int | None, article_branch_no: int | None) -> str | None:
    if not law_name or article_no is None:
        return None
    if article_branch_no:
        return f"{law_name} 제{article_no}조의{article_branch_no}"
    return f"{law_name} 제{article_no}조"


def legal_evidence_ref(evidence: dict[str, Any]) -> tuple[str, int | None, int | None]:
    law_name = evidence.get("law_name") or evidence.get("related_law_name") or evidence.get("source_name") or ""
    article_no = evidence.get("article_no") or evidence.get("related_article_no")
    article_branch_no = evidence.get("article_branch_no")
    title_ref = parse_legal_basis_ref(str(evidence.get("title") or ""))
    try:
        article_no = int(article_no) if article_no is not None else None
    except (TypeError, ValueError):
        article_no = None
    try:
        article_branch_no = int(article_branch_no) if article_branch_no is not None else None
    except (TypeError, ValueError):
        article_branch_no = None
    if title_ref is not None:
        title_law_name, title_article_no, title_branch_no = title_ref
        if article_no is None or article_no == title_article_no:
            article_no = title_article_no
            article_branch_no = title_branch_no if title_branch_no is not None else article_branch_no
        if not law_name:
            law_name = title_law_name
    return re.sub(r"\s+", "", str(law_name)), article_no, article_branch_no


def display_law_name(evidence: dict[str, Any]) -> str:
    return str(evidence.get("law_name") or evidence.get("related_law_name") or evidence.get("source_name") or "").strip()


def find_basis_evidence(basis: str, analysis_item: dict[str, Any]) -> dict[str, Any] | None:
    parsed = parse_legal_basis_ref(basis)
    if parsed is None:
        return None

    target_law, target_article, target_branch = parsed
    evidence_rows = [
        *(analysis_item.get("legal_evidence") or []),
        *(analysis_item.get("guidance_evidence") or []),
    ]

    for evidence in evidence_rows:
        law_name, article_no, article_branch_no = legal_evidence_ref(evidence)
        if law_name != target_law or article_no != target_article:
            continue
        if target_branch is None:
            if article_branch_no in (None, 0):
                return evidence
            continue
        if article_branch_no == target_branch:
            return evidence
    return None


def detail_from_evidence(evidence: dict[str, Any], basis: str | None = None) -> dict[str, Any] | None:
    law_name_key, article_no, article_branch_no = legal_evidence_ref(evidence)
    legal_basis = basis or format_legal_basis(display_law_name(evidence) or law_name_key, article_no, article_branch_no)
    text = evidence.get("chunk_text")
    if not legal_basis or not text:
        return None
    return {
        "basis": legal_basis,
        "title": evidence.get("title") or legal_basis,
        "law_name": display_law_name(evidence) or law_name_key,
        "article_no": article_no,
        "article_branch_no": article_branch_no,
        "text": text,
        "source_name": evidence.get("source_name"),
        "similarity": to_float(evidence.get("similarity")) if evidence.get("similarity") is not None else None,
    }


def collect_candidate_legal_basis_details(analysis_item: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not analysis_item:
        return []

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    evidence_rows = [
        *(analysis_item.get("legal_evidence") or []),
        *(analysis_item.get("guidance_evidence") or []),
    ]
    for evidence in evidence_rows:
        detail = detail_from_evidence(evidence)
        if not detail:
            continue
        key = detail["basis"]
        if key in seen:
            continue
        seen.add(key)
        candidates.append(detail)
    return candidates


def build_legal_basis_details(
    legal_basis: list[str],
    analysis_item: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not analysis_item:
        return []

    details: list[dict[str, Any]] = []
    seen: set[str] = set()
    for basis in legal_basis:
        if not isinstance(basis, str) or basis in seen:
            continue
        seen.add(basis)
        evidence = find_basis_evidence(basis, analysis_item)
        if not evidence:
            continue
        detail = detail_from_evidence(evidence, basis=basis)
        if detail:
            details.append(detail)
    return details


def attach_legal_basis_details(payload: dict[str, Any], analysis_result: dict[str, Any]) -> dict[str, Any]:
    condition_items = [
        item
        for item in payload.get("analysis_items", [])
        if item.get("item_type") == "contract_condition"
    ]
    condition_item_by_label = {
        item.get("label"): item
        for item in condition_items
        if item.get("label")
    }
    condition_item_by_field_path = {
        item.get("field_path"): item
        for item in condition_items
        if item.get("field_path") and item.get("legal_evidence")
    }
    special_item_by_order = {
        item.get("special_term_order"): item
        for item in payload.get("analysis_items", [])
        if item.get("item_type") == "special_term" and item.get("special_term_order") is not None
    }

    for index, item in enumerate(analysis_result.get("contract_conditions") or []):
        if not isinstance(item, dict):
            continue
        analysis_item = condition_item_by_label.get(item.get("label"))
        if analysis_item is None and index < len(condition_items):
            analysis_item = condition_items[index]
        details = build_legal_basis_details(item.get("legal_basis") or [], analysis_item)
        if len(details) < len(item.get("legal_basis") or []) and analysis_item is not None:
            fallback_item = condition_item_by_field_path.get(analysis_item.get("field_path"))
            if fallback_item is not analysis_item:
                fallback_details = build_legal_basis_details(item.get("legal_basis") or [], fallback_item)
                seen_basis = {detail.get("basis") for detail in details}
                details.extend(detail for detail in fallback_details if detail.get("basis") not in seen_basis)
        item["legal_basis_details"] = details

    for item in analysis_result.get("special_terms") or []:
        if not isinstance(item, dict):
            continue
        analysis_item = special_item_by_order.get(item.get("order"))
        item["legal_basis_details"] = build_legal_basis_details(item.get("legal_basis") or [], analysis_item)

    return analysis_result


def analysis_items_by_label_and_order(payload: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[int, dict[str, Any]]]:
    by_label = {
        item.get("label"): item
        for item in payload.get("analysis_items", [])
        if item.get("item_type") == "contract_condition" and item.get("label")
    }
    by_order = {
        item.get("special_term_order"): item
        for item in payload.get("analysis_items", [])
        if item.get("item_type") == "special_term" and item.get("special_term_order") is not None
    }
    return by_label, by_order


def build_legal_basis_verification_payload(payload: dict[str, Any], analysis_result: dict[str, Any]) -> dict[str, Any]:
    condition_items_by_label, special_items_by_order = analysis_items_by_label_and_order(payload)

    contract_conditions = []
    for item in analysis_result.get("contract_conditions") or []:
        if not isinstance(item, dict):
            continue
        analysis_item = condition_items_by_label.get(item.get("label"))
        candidates = collect_candidate_legal_basis_details(analysis_item)
        if not candidates:
            continue
        contract_conditions.append(
            {
                "label": item.get("label"),
                "judgment": item.get("judgment"),
                "reason": item.get("reason"),
                "query_text": analysis_item.get("query_text") if analysis_item else None,
                "candidate_legal_basis": candidates,
            }
        )

    special_terms = []
    for item in analysis_result.get("special_terms") or []:
        if not isinstance(item, dict):
            continue
        analysis_item = special_items_by_order.get(item.get("order"))
        candidates = collect_candidate_legal_basis_details(analysis_item)
        if not candidates:
            continue
        special_terms.append(
            {
                "order": item.get("order"),
                "label": item.get("label"),
                "judgment": item.get("judgment"),
                "reason": item.get("reason"),
                "query_text": analysis_item.get("query_text") if analysis_item else None,
                "candidate_legal_basis": candidates,
            }
        )

    return {
        "task": "verify_legal_basis_relevance_for_contract_analysis",
        "instructions": (
            "각 분석 항목의 judgment/reason/query_text와 후보 법령의 조문 내용을 비교해, "
            "후보 법령이 해당 분석의 근거로 직접 맞는지 검증한다. "
            "direct는 판단을 직접 뒷받침하는 조문, supporting은 배경 또는 간접 참고로만 유용한 조문, "
            "irrelevant는 해당 분석 근거로 쓰기 부적절한 조문이다. "
            "비슷한 주제라도 분석 이유를 직접 뒷받침하지 않으면 supporting 또는 irrelevant로 낮춰라. "
            "후보에 없는 법령은 새로 만들지 말고, candidate_legal_basis의 basis/title만 사용하라."
        ),
        "contract_conditions": contract_conditions,
        "special_terms": special_terms,
    }


def build_legal_basis_verification_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": (
                "너는 한국 주택 임대차 계약 분석에서 법령 근거의 적합성을 검증하는 보조 시스템이다. "
                "후보 조문 내용과 분석 문장을 대조해 direct/supporting/irrelevant를 엄격히 분류한다. "
                "반드시 JSON만 출력한다."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, indent=2, default=json_default),
        },
    ]


def verify_legal_basis_relevance(
    verification_payload: dict[str, Any],
    client: OpenAI,
    analysis_model: str,
) -> dict[str, Any]:
    response = client.responses.create(
        model=analysis_model,
        input=build_legal_basis_verification_messages(verification_payload),
        text={
            "format": {
                "type": "json_schema",
                "name": "legal_basis_verification_result",
                "schema": LEGAL_BASIS_VERIFICATION_SCHEMA,
                "strict": True,
            }
        },
    )
    return json.loads(response.output_text)


def candidate_lookup_by_item(payload: dict[str, Any]) -> tuple[dict[str, dict[tuple[str, str], dict[str, Any]]], dict[int, dict[tuple[str, str], dict[str, Any]]]]:
    condition_items_by_label, special_items_by_order = analysis_items_by_label_and_order(payload)

    condition_lookup = {
        label: {
            (detail["basis"], detail["title"]): detail
            for detail in collect_candidate_legal_basis_details(item)
        }
        for label, item in condition_items_by_label.items()
    }
    special_lookup = {
        int(order): {
            (detail["basis"], detail["title"]): detail
            for detail in collect_candidate_legal_basis_details(item)
        }
        for order, item in special_items_by_order.items()
        if isinstance(order, int)
    }
    return condition_lookup, special_lookup


def apply_legal_basis_verification(
    analysis_result: dict[str, Any],
    llm_payload: dict[str, Any],
    verification_result: dict[str, Any],
) -> dict[str, Any]:
    condition_lookup, special_lookup = candidate_lookup_by_item(llm_payload)
    condition_reviews = {
        item.get("label"): item.get("legal_basis_reviews") or []
        for item in verification_result.get("contract_conditions") or []
        if item.get("label")
    }
    special_reviews = {
        item.get("order"): item.get("legal_basis_reviews") or []
        for item in verification_result.get("special_terms") or []
        if item.get("order") is not None
    }

    def verified_details(reviews: list[dict[str, Any]], lookup: dict[tuple[str, str], dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
        basis_list: list[str] = []
        details: list[dict[str, Any]] = []
        all_reviews: list[dict[str, Any]] = []
        seen_reviews: set[tuple[str, str]] = set()
        seen_kept_basis: set[str] = set()
        for review in reviews:
            basis = review.get("basis")
            title = review.get("title")
            review_key = (str(basis), str(title))
            if review_key in seen_reviews:
                continue
            seen_reviews.add(review_key)
            detail = lookup.get((basis, title))
            if detail is None:
                continue
            enriched_review = {
                "basis": basis,
                "title": title,
                "relevance": review.get("relevance"),
                "confidence": review.get("confidence"),
                "why_relevant": review.get("why_relevant"),
            }
            all_reviews.append(enriched_review)
            if review.get("relevance") == "irrelevant":
                continue
            if str(basis) in seen_kept_basis:
                continue
            seen_kept_basis.add(str(basis))
            next_detail = dict(detail)
            next_detail["relevance"] = review.get("relevance")
            next_detail["confidence"] = review.get("confidence")
            next_detail["why_relevant"] = review.get("why_relevant")
            basis_list.append(str(basis))
            details.append(next_detail)
        return basis_list, details, all_reviews

    for item in analysis_result.get("contract_conditions") or []:
        if not isinstance(item, dict):
            continue
        reviews = condition_reviews.get(item.get("label"), [])
        lookup = condition_lookup.get(item.get("label"), {})
        basis_list, details, all_reviews = verified_details(reviews, lookup)
        item["legal_basis"] = basis_list
        item["legal_basis_details"] = details
        item["legal_basis_reviews"] = all_reviews

    for item in analysis_result.get("special_terms") or []:
        if not isinstance(item, dict):
            continue
        reviews = special_reviews.get(item.get("order"), [])
        lookup = special_lookup.get(item.get("order"), {})
        basis_list, details, all_reviews = verified_details(reviews, lookup)
        item["legal_basis"] = basis_list
        item["legal_basis_details"] = details
        item["legal_basis_reviews"] = all_reviews

    analysis_result["legal_basis_verification"] = {
        "status": "success",
        "mode": "llm_second_pass",
    }
    return analysis_result


def persist_rag_artifacts(output_dir: str | Path, rag_result: dict[str, Any], llm_payload: dict[str, Any], analysis_result: dict[str, Any]) -> dict[str, str]:
    output_root = Path(output_dir)
    rag_result_path = output_root / "rag_result.json"
    llm_payload_path = output_root / "rag_llm_payload.json"
    llm_analysis_path = output_root / "rag_analysis_result.json"

    with open(rag_result_path, "w", encoding="utf-8") as file:
        json.dump(rag_result, file, ensure_ascii=False, indent=2, default=json_default)
    with open(llm_payload_path, "w", encoding="utf-8") as file:
        json.dump(llm_payload, file, ensure_ascii=False, indent=2, default=json_default)
    save_json(llm_analysis_path, analysis_result)

    return {
        "rag_result_path": str(rag_result_path),
        "rag_payload_path": str(llm_payload_path),
        "rag_analysis_path": str(llm_analysis_path),
    }


def analyze_contract_with_rag(
    contract: dict[str, Any],
    output_dir: str | Path | None = None,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    analysis_model: str = DEFAULT_ANALYSIS_MODEL,
) -> dict[str, Any]:
    client = get_openai_client()
    rag_result = run_rag_search(contract, client=client, embedding_model=embedding_model)
    llm_payload = build_llm_payload(contract, rag_result)
    analysis_result = generate_analysis_from_payload(llm_payload, client=client, analysis_model=analysis_model)
    analysis_result = normalize_analysis_labels(llm_payload, analysis_result)
    analysis_result = normalize_condition_judgments(analysis_result)
    analysis_result = attach_legal_basis_details(llm_payload, analysis_result)
    legal_basis_verification_payload = build_legal_basis_verification_payload(llm_payload, analysis_result)
    try:
        legal_basis_verification_result = verify_legal_basis_relevance(
            legal_basis_verification_payload,
            client=client,
            analysis_model=analysis_model,
        )
        analysis_result = apply_legal_basis_verification(
            analysis_result,
            llm_payload=llm_payload,
            verification_result=legal_basis_verification_result,
        )
    except Exception as exc:
        analysis_result["legal_basis_verification"] = {
            "status": "failed",
            "error_message": str(exc),
        }

    output_paths: dict[str, str] = {}
    if output_dir is not None:
        output_paths = persist_rag_artifacts(output_dir, rag_result, llm_payload, analysis_result)

    return {
        "status": "success",
        "embedding_model": embedding_model,
        "analysis_model": analysis_model,
        "rag_result": rag_result,
        "llm_payload": llm_payload,
        "analysis_result": analysis_result,
        "output_paths": output_paths,
    }

RAG_CONDITION_FIELD_PATHS = {
    "보증금 조건": "payment.deposit",
    "잔금 조건": "payment.balance",
    "월 차임 조건": "payment.monthly_rent",
    "차임 지급 방식": "payment.monthly_due_day",
    "임대차 기간 조건": "contract_terms[article_no=제2조].content",
    "임대차 기간 확인": "contract_terms[article_no=제2조].content",
    "목적물 표시": "property.leased_part.raw_text",
    "전세/월세 유형 확인": "lease_type",
    "잔금 구조 확인": "payment.balance",
    "보증금 합계 확인": "payment.deposit",
    "중도금 기재 확인": "payment.intermediate_money",
}

REVIEW_LEVELS = {"양호", "보통", "주의"}
STRONG_CAUTION_TOKENS = ("불리", "주의", "확인 필요", "위험", "불명확", "분쟁")
NEUTRAL_TOKENS = ("중립", "보통", "확인 권장")
POSITIVE_TOKENS = ("유리", "양호", "무난", "문제 없음", "적정")


def judgment_to_review_level(judgment: str | None) -> str:
    text = (judgment or "").strip()
    if not text:
        return "보통"
    if any(token in text for token in STRONG_CAUTION_TOKENS):
        return "주의"
    if any(token in text for token in NEUTRAL_TOKENS):
        return "보통"
    return "양호"


def normalize_review_level(review_level: str | None, judgment: str | None = None) -> str:
    text = (judgment or "").strip()
    if any(token in text for token in STRONG_CAUTION_TOKENS + NEUTRAL_TOKENS + POSITIVE_TOKENS):
        return judgment_to_review_level(text)
    if review_level in REVIEW_LEVELS:
        return review_level
    return judgment_to_review_level(text)

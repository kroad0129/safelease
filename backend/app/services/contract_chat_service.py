import json
from pathlib import Path
from typing import Any

import psycopg
from openai import OpenAI

from app.core.common import OUTPUT_DIR
from app.services.rag_analysis_service import (
    DEFAULT_ANALYSIS_MODEL,
    DEFAULT_EMBEDDING_MODEL,
    build_search_topics,
    fetch_chunk_matches,
    fetch_clause_matches,
    get_connection_string,
    get_openai_client,
    infer_topic,
    json_default,
)


CHAT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["analysis_explanation", "risk_question", "clause_recommendation", "legal_question", "rewrite_request", "general"],
        },
        "answer": {"type": "string"},
        "related_contract_points": {"type": "array", "items": {"type": "string"}},
        "recommended_clauses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "clause_text": {"type": "string"},
                    "why": {"type": "string"},
                    "tenant_benefit": {"type": "string"},
                    "negotiation_note": {"type": "string"},
                },
                "required": ["title", "clause_text", "why", "tenant_benefit", "negotiation_note"],
                "additionalProperties": False,
            },
        },
        "legal_basis": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "basis": {"type": "string"},
                    "title": {"type": "string"},
                    "text": {"type": "string"},
                    "relevance": {"type": "string", "enum": ["direct", "supporting"]},
                },
                "required": ["basis", "title", "text", "relevance"],
                "additionalProperties": False,
            },
        },
        "cautions": {"type": "array", "items": {"type": "string"}},
        "follow_up_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "intent",
        "answer",
        "related_contract_points",
        "recommended_clauses",
        "legal_basis",
        "cautions",
        "follow_up_questions",
    ],
    "additionalProperties": False,
}


FAVORABLE_CLAUSE_TEMPLATES = [
    {
        "topic": "pet",
        "title": "반려동물 사육 허용 및 책임 범위",
        "clause_text": (
            "임대인은 임차인이 사전 고지한 반려동물 1마리의 사육에 동의한다. "
            "임차인은 반려동물로 인해 발생한 벽지, 바닥, 문, 설비 등의 직접적인 훼손에 대해서만 "
            "퇴거 시 원상회복 또는 상당액을 부담한다. 단, 통상 사용에 따른 마모나 반려동물과 "
            "무관한 하자는 임차인의 책임으로 보지 않는다."
        ),
        "why": "반려동물 허용 여부와 책임 범위를 함께 정해 과도한 배상 부담을 피하게 합니다.",
    },
    {
        "topic": "deposit_return",
        "title": "보증금 반환과 인도 동시이행",
        "clause_text": "임대인은 임대차 종료일에 보증금 전액을 반환하고, 임차인은 보증금 반환과 동시에 주택을 인도한다.",
        "why": "보증금 반환 전 퇴거를 요구받는 위험을 줄입니다.",
    },
    {
        "topic": "priority_protection",
        "title": "전입신고 및 확정일자 보장",
        "clause_text": (
            "임대인은 임차인의 전입신고 및 확정일자 취득을 방해하지 않으며, "
            "임차인이 대항력과 우선변제권을 취득하는 다음 날까지 새로운 담보권 또는 선순위 권리를 설정하지 않는다."
        ),
        "why": "보증금 보호에 필요한 절차를 계약상 명확히 보장합니다.",
    },
    {
        "topic": "repair_and_defect",
        "title": "노후 설비와 입주 전 하자 보수",
        "clause_text": (
            "입주 전 확인된 누수, 보일러, 배관, 전기설비 등 주요 하자는 임대인이 인도 전까지 보수한다. "
            "임차인의 고의 또는 과실이 없는 노후 설비 고장은 임대인이 수리한다."
        ),
        "why": "모든 수리비가 임차인에게 전가되는 상황을 막습니다.",
    },
    {
        "topic": "management_fee",
        "title": "관리비 항목과 정산 기준 명시",
        "clause_text": "관리비는 항목, 월 금액, 포함 내역, 별도 사용료 및 정산 방식을 계약서 또는 별지에 명확히 기재한다.",
        "why": "관리비 임의 인상이나 불명확한 공제를 예방합니다.",
    },
    {
        "topic": "insurance_and_guarantee",
        "title": "보증보험 가입 협조",
        "clause_text": "임차인이 전세보증금 반환보증 등 보증금 보호 절차를 신청하는 경우 임대인은 필요한 서류 제공에 협조한다.",
        "why": "보증금 회수 안전장치를 확보하는 데 도움이 됩니다.",
    },
]


def resolve_output_artifact_path(public_url: str) -> Path:
    if not public_url.startswith("/outputs/"):
        raise ValueError("분석 결과 파일 경로가 올바르지 않습니다.")
    relative = Path(*public_url.removeprefix("/outputs/").split("/"))
    path = (OUTPUT_DIR / relative).resolve()
    output_root = OUTPUT_DIR.resolve()
    if output_root not in path.parents:
        raise ValueError("분석 결과 파일 경로가 허용 범위를 벗어났습니다.")
    if path.name != "combined_result.json":
        raise ValueError("combined_result.json만 챗봇 컨텍스트로 사용할 수 있습니다.")
    if not path.exists():
        raise FileNotFoundError("분석 결과 파일을 찾을 수 없습니다.")
    return path


def load_combined_result(public_url: str) -> dict[str, Any]:
    path = resolve_output_artifact_path(public_url)
    return json.loads(path.read_text(encoding="utf-8"))


def text_value(node: Any, *keys: str) -> Any:
    value = node
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    if isinstance(value, dict):
        return value.get("value") or value.get("raw_text") or value.get("normalized_value")
    return value


def build_chat_context(combined_result: dict[str, Any]) -> dict[str, Any]:
    extracted = combined_result.get("extracted") or {}
    verification = combined_result.get("verification") or {}
    rag_analysis = (combined_result.get("rag_analysis") or {}).get("summary") or {}
    payment = extracted.get("payment") or {}
    property_info = extracted.get("property") or {}

    return {
        "contract_snapshot": {
            "lease_type": extracted.get("lease_type"),
            "property_address": text_value(property_info, "address"),
            "leased_part": text_value(property_info, "leased_part"),
            "deposit": text_value(payment, "deposit"),
            "contract_money": text_value(payment, "contract_money"),
            "balance": text_value(payment, "balance"),
            "monthly_rent": text_value(payment, "monthly_rent"),
            "rent_payment_type": text_value(payment, "rent_payment_type"),
            "monthly_due_day": text_value(payment, "monthly_due_day"),
        },
        "contract_terms": extracted.get("contract_terms", [])[:12],
        "special_terms": extracted.get("special_terms", [])[:20],
        "verification_findings": ((verification.get("analysis") or {}).get("findings") or [])[:8],
        "rag_contract_conditions": (rag_analysis.get("contract_conditions") or [])[:12],
        "rag_special_terms": (rag_analysis.get("special_terms") or [])[:20],
        "overall_summary": rag_analysis.get("overall_summary") or {},
    }


def embed_query(client: OpenAI, model: str, text: str) -> list[float]:
    response = client.embeddings.create(model=model, input=[text])
    return response.data[0].embedding


def preferred_favorable_templates(question: str, topic: str) -> list[dict[str, str]]:
    rows = []
    pet_keywords = ["반려동물", "반려견", "반려묘", "강아지", "고양이", "애완동물", "펫"]
    if topic == "pet" or any(keyword in question for keyword in pet_keywords):
        return [item for item in FAVORABLE_CLAUSE_TEMPLATES if item["topic"] == "pet"][:1]

    for item in FAVORABLE_CLAUSE_TEMPLATES:
        if item["topic"] == topic or item["title"] in question:
            rows.append(item)
    if not rows and any(keyword in question for keyword in ["유리", "추천", "특약", "문구"]):
        rows = FAVORABLE_CLAUSE_TEMPLATES[:4]
    return rows[:4]


def normalize_chat_answer(answer: dict[str, Any], rag: dict[str, Any]) -> dict[str, Any]:
    normalized_clauses = []
    seen_titles = set()
    for clause in answer.get("recommended_clauses") or []:
        title = str(clause.get("title") or "").strip()
        clause_text = str(clause.get("clause_text") or "").strip()
        if not title or not clause_text or len(clause_text) < 25 or title in seen_titles:
            continue
        seen_titles.add(title)
        normalized_clauses.append(
            {
                "title": title,
                "clause_text": clause_text,
                "why": str(clause.get("why") or "").strip(),
                "tenant_benefit": str(clause.get("tenant_benefit") or "").strip(),
                "negotiation_note": str(clause.get("negotiation_note") or "").strip(),
            }
        )

    favorite_templates = rag.get("favorable_templates") or []
    if favorite_templates and not normalized_clauses:
        template = favorite_templates[0]
        normalized_clauses.append(
            {
                "title": template["title"],
                "clause_text": template["clause_text"],
                "why": template["why"],
                "tenant_benefit": "허용 범위와 책임 범위를 명확히 해 임차인에게 과도한 부담이 생기는 것을 줄입니다.",
                "negotiation_note": "상황에 따라 '소형견 1마리', '고양이 1마리', '사전 서면 동의한 반려동물 1마리'처럼 조정할 수 있습니다.",
            }
        )

    answer["recommended_clauses"] = normalized_clauses[:3]
    return answer


def fetch_chat_rag(question: str, client: OpenAI, embedding_model: str) -> dict[str, Any]:
    topic = infer_topic(question)
    topics = build_search_topics(topic, "clause")
    vector = embed_query(client, embedding_model, question)
    with psycopg.connect(get_connection_string()) as conn:
        legal_matches = fetch_chunk_matches(
            conn,
            embedding_model=embedding_model,
            query_vector=vector,
            topics=topics,
            limit=6,
            law_only=True,
        )
        clause_matches = fetch_clause_matches(
            conn,
            embedding_model=embedding_model,
            query_vector=vector,
            topics=topics,
            limit=6,
        )
    return {
        "topic": topic,
        "legal_matches": [
            {
                "basis": f"{row.get('law_name')} 제{row.get('article_no')}조"
                + (f"의{row.get('article_branch_no')}" if row.get("article_branch_no") else ""),
                "title": row.get("title"),
                "text": row.get("chunk_text"),
                "similarity": row.get("similarity"),
            }
            for row in legal_matches[:4]
        ],
        "similar_clauses": [
            {
                "title": row.get("title"),
                "text": row.get("raw_text"),
                "favorability": row.get("favorability"),
                "risk_level": row.get("risk_level"),
                "similarity": row.get("similarity"),
            }
            for row in clause_matches[:4]
        ],
        "favorable_templates": preferred_favorable_templates(question, topic),
    }


def build_chat_messages(
    question: str,
    context: dict[str, Any],
    rag: dict[str, Any],
    history: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    compact_history = (history or [])[-6:]
    return [
        {
            "role": "system",
            "content": (
                "너는 임차인 보호 중심의 주택임대차 계약 Q&A 도우미다. "
                "반드시 제공된 계약서 분석 결과와 검색 근거 안에서 답하고, 모르면 확인 필요라고 말한다. "
                "특약 추천 요청이면 임차인에게 유리하지만 임대인과 협상 가능한 문구를 제안한다. "
                "법률 자문을 단정하지 말고 실무 검토 관점으로 설명한다. JSON만 출력한다."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": question,
                    "recent_chat_history": compact_history,
                    "contract_analysis_context": context,
                    "rag_evidence": rag,
                    "answer_rules": [
                        "answer는 좁은 챗봇 말풍선에 들어갈 2~3문장 요약으로만 작성한다.",
                        "특약 전문과 세부 설명은 recommended_clauses 배열에만 넣고 answer에 반복하지 않는다.",
                        "특약 추천 질문이면 가장 바로 쓸 수 있는 완성형 특약 1개를 먼저 제안한다.",
                        "recommended_clauses는 꼭 필요한 경우에만 최대 3개까지 제안한다.",
                        "recommended_clauses에 넣는 모든 항목은 title, why, clause_text, negotiation_note가 모두 실제 내용이어야 한다.",
                        "clause_text가 없는 제목만 있는 추천은 절대 만들지 않는다.",
                        "현재 계약서에 이미 있는 내용과 없는 내용을 구분한다.",
                        "추천 특약은 바로 붙여 넣을 수 있는 문장으로 작성한다.",
                        "반려동물 특약은 허용 범위, 직접 훼손 책임, 통상 마모 제외를 포함한다.",
                        "근거 법령은 후보 중 질문과 관련 있는 것만 사용한다.",
                        "위험특약 예시는 그대로 추천하지 말고 위험 회피 방향으로 바꿔 제안한다.",
                    ],
                },
                ensure_ascii=False,
                indent=2,
                default=json_default,
            ),
        },
    ]


def ask_contract_chat(
    combined_result_url: str,
    question: str,
    history: list[dict[str, str]] | None = None,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    analysis_model: str = DEFAULT_ANALYSIS_MODEL,
) -> dict[str, Any]:
    if not question.strip():
        raise ValueError("질문을 입력해주세요.")
    combined_result = load_combined_result(combined_result_url)
    context = build_chat_context(combined_result)
    client = get_openai_client()
    rag = fetch_chat_rag(question, client, embedding_model)
    response = client.responses.create(
        model=analysis_model,
        input=build_chat_messages(question, context, rag, history),
        text={
            "format": {
                "type": "json_schema",
                "name": "contract_chat_answer",
                "schema": CHAT_OUTPUT_SCHEMA,
                "strict": True,
            }
        },
    )
    answer = json.loads(response.output_text)
    answer = normalize_chat_answer(answer, rag)
    answer["rag"] = {
        "topic": rag.get("topic"),
        "legal_count": len(rag.get("legal_matches") or []),
        "clause_count": len(rag.get("similar_clauses") or []),
    }
    return answer

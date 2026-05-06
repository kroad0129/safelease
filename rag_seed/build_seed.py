import argparse
import hashlib
import http.client
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASE_SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
BASE_SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "dist"

CORE_REFS: dict[str, list[tuple[int, int]]] = {
    "주택임대차보호법": [
        (2, 0),
        (3, 0),
        (3, 1),
        (3, 2),
        (3, 3),
        (3, 4),
        (3, 5),
        (3, 7),
        (4, 0),
        (6, 0),
        (6, 2),
        (6, 3),
        (7, 0),
        (7, 2),
        (8, 0),
        (8, 2),
        (10, 0),
        (10, 2),
        (30, 0),
    ],
    "주택임대차보호법 시행령": [
        (10, 0),
        (11, 0),
        (14, 0),
        (17, 0),
    ],
    "민법": [
        (390, 0),
        (543, 0),
        (544, 0),
        (545, 0),
        (548, 0),
        (565, 0),
        (618, 0),
        (623, 0),
        (624, 0),
        (625, 0),
        (626, 0),
        (627, 0),
        (628, 0),
        (629, 0),
        (630, 0),
        (633, 0),
        (634, 0),
        (635, 0),
        (636, 0),
        (640, 0),
        (652, 0),
    ],
    "공인중개사법": [
        (25, 0),
        (25, 2),
        (25, 3),
        (30, 0),
        (32, 0),
        (33, 0),
    ],
    "공인중개사법 시행규칙": [
        (16, 0),
        (20, 0),
    ],
    "부동산 거래신고 등에 관한 법률": [
        (6, 2),
        (6, 3),
        (6, 4),
        (28, 0),
    ],
}

LAW_TOPIC_RULES: list[tuple[str, str, list[str]]] = [
    ("priority_protection", "legal_basis", ["대항력", "우선변제", "확정일자", "임차권등기", "최우선변제", "소액보증금"]),
    ("lease_period", "legal_basis", ["기간", "존속기간", "묵시", "갱신", "계약갱신", "해지통고"]),
    ("rent_increase", "legal_basis", ["차임", "증감", "월차임", "증액", "전환"]),
    ("deposit_return", "legal_basis", ["보증금", "반환", "동시이행", "공탁"]),
    ("repair_and_defect", "legal_basis", ["수선", "보존", "필요비", "유익비", "하자"]),
    ("sublease_and_transfer", "legal_basis", ["전대", "양도"]),
    ("broker_duty", "legal_basis", ["중개대상물", "확인", "설명", "거래계약서", "중개보수", "금지행위"]),
    ("lease_reporting", "legal_basis", ["신고", "주택 임대차 계약"]),
]

TENANT_RISK_CLAUSES: list[dict[str, str]] = [
    {"topic": "deposit_return", "risk_level": "high", "title": "보증금 반환 전 명도 요구", "raw_text": "임차인은 임대차 종료일에 보증금 반환 여부와 관계없이 즉시 주택을 인도한다.", "recommended_revision": "임차인은 임대인이 보증금 전액을 반환함과 동시에 주택을 인도한다."},
    {"topic": "deposit_return", "risk_level": "high", "title": "보증금 반환 지연 면책", "raw_text": "임대인은 사정에 따라 보증금 반환을 지연할 수 있으며 임차인은 이에 이의를 제기하지 않는다.", "recommended_revision": "임대인은 임대차 종료 시 보증금을 지체 없이 반환하고, 지연 시 법정 지연손해금을 부담한다."},
    {"topic": "deposit_return", "risk_level": "high", "title": "새 임차인 전까지 반환 유예", "raw_text": "보증금은 새로운 임차인이 구해진 후 반환한다.", "recommended_revision": "보증금 반환은 새 임차인 모집 여부와 무관하게 임대차 종료일에 이행한다."},
    {"topic": "priority_protection", "risk_level": "high", "title": "전입신고 제한", "raw_text": "임차인은 임대인의 동의 없이 전입신고를 할 수 없다.", "recommended_revision": "임차인은 입주 즉시 전입신고와 확정일자를 받을 수 있다."},
    {"topic": "priority_protection", "risk_level": "high", "title": "확정일자 제한", "raw_text": "임차인은 계약 체결 후 30일이 지난 뒤 확정일자를 받기로 한다.", "recommended_revision": "임차인은 계약 체결 및 잔금 지급 즉시 확정일자를 받을 수 있다."},
    {"topic": "priority_protection", "risk_level": "high", "title": "선순위 담보 설정 허용", "raw_text": "임대인은 잔금 지급 전후 필요한 경우 담보대출을 설정할 수 있다.", "recommended_revision": "임대인은 임차인의 대항력과 우선변제권 취득 다음 날까지 새로운 담보권을 설정하지 않는다."},
    {"topic": "priority_protection", "risk_level": "high", "title": "권리변동 통지 면제", "raw_text": "임대인은 계약 후 권리관계 변동이 있더라도 임차인에게 별도 통지하지 않는다.", "recommended_revision": "임대인은 계약 후 권리제한, 압류, 가압류, 담보권 설정 등 변동을 즉시 서면 통지한다."},
    {"topic": "registry_and_rights", "risk_level": "medium", "title": "등기부 확인 책임 전가", "raw_text": "임차인은 등기부상 권리관계를 모두 확인하였으므로 이후 권리문제는 임차인이 책임진다.", "recommended_revision": "임대인은 계약 체결일과 잔금일의 권리관계가 다를 경우 임차인에게 즉시 알리고 협의한다."},
    {"topic": "repair_and_defect", "risk_level": "high", "title": "모든 수리비 임차인 부담", "raw_text": "임대차기간 중 발생하는 모든 수리비와 하자보수 비용은 원인과 무관하게 임차인이 부담한다.", "recommended_revision": "임차인의 고의·과실 손상은 임차인이, 노후화·구조적 하자는 임대인이 부담한다."},
    {"topic": "repair_and_defect", "risk_level": "high", "title": "입주 전 하자 책임 면제", "raw_text": "입주 전 발견된 하자도 임차인이 인수하며 임대인은 보수 책임을 지지 않는다.", "recommended_revision": "입주 전 확인된 하자는 인도 전까지 임대인이 보수한다."},
    {"topic": "repair_and_defect", "risk_level": "medium", "title": "누수 책임 임차인 부담", "raw_text": "누수, 결로, 곰팡이 등은 모두 임차인이 관리하지 못한 책임으로 본다.", "recommended_revision": "누수 등 구조적 원인은 임대인이 보수하고, 환기·사용상 과실은 임차인이 부담한다."},
    {"topic": "repair_and_defect", "risk_level": "medium", "title": "보일러 수리비 임차인 부담", "raw_text": "보일러, 배관, 전기시설 고장 수리비는 임차인이 전액 부담한다.", "recommended_revision": "주요 설비의 노후·통상 사용 중 고장은 임대인이 보수한다."},
    {"topic": "restoration", "risk_level": "high", "title": "과도한 원상복구", "raw_text": "임차인은 사용 여부와 관계없이 도배, 장판, 싱크대, 욕실을 모두 신품으로 교체한다.", "recommended_revision": "임차인은 통상 손모를 제외하고 고의·과실로 훼손한 부분만 원상회복한다."},
    {"topic": "restoration", "risk_level": "medium", "title": "자연마모 배상", "raw_text": "자연적인 노후나 통상 사용으로 인한 마모도 임차인이 배상한다.", "recommended_revision": "통상 사용에 따른 자연마모는 임차인의 배상 범위에서 제외한다."},
    {"topic": "restoration", "risk_level": "medium", "title": "청소비 일괄 공제", "raw_text": "퇴거 시 임대인은 보증금에서 청소비 100만원을 일괄 공제한다.", "recommended_revision": "청소비는 실제 미이행 상태와 합리적 비용 증빙에 따라 정산한다."},
    {"topic": "management_fee", "risk_level": "medium", "title": "관리비 세부내역 미기재", "raw_text": "관리비는 매월 임대인이 정하는 금액으로 납부한다.", "recommended_revision": "관리비 항목, 금액, 정산 방식과 변동 기준을 계약서에 명확히 기재한다."},
    {"topic": "management_fee", "risk_level": "medium", "title": "관리비 임의 인상", "raw_text": "임대인은 필요 시 관리비를 임의로 인상할 수 있다.", "recommended_revision": "관리비 인상은 실제 비용 증가 자료를 기준으로 사전 통지 후 협의한다."},
    {"topic": "payment_schedule", "risk_level": "medium", "title": "차임 선납 과다", "raw_text": "임차인은 1년치 월세를 계약 체결 시 선납한다.", "recommended_revision": "차임은 월별 지급을 원칙으로 하고 선납이 필요한 경우 반환 조건을 명확히 한다."},
    {"topic": "payment_schedule", "risk_level": "medium", "title": "연체 즉시 해지", "raw_text": "월세가 1일이라도 늦으면 임대인은 즉시 계약을 해지할 수 있다.", "recommended_revision": "차임 연체 해지는 법정 기준과 최고 절차를 고려해 정한다."},
    {"topic": "payment_schedule", "risk_level": "medium", "title": "계좌 변경 구두 통지", "raw_text": "임대인은 월세 입금 계좌를 구두로 변경할 수 있다.", "recommended_revision": "계좌 변경은 임대인 본인 확인 가능한 서면 또는 문자로 통지한다."},
    {"topic": "early_termination", "risk_level": "high", "title": "중도해지 위약금 과다", "raw_text": "임차인이 중도해지하면 남은 기간 월세 전액을 위약금으로 지급한다.", "recommended_revision": "중도해지 위약금은 실제 손해와 재임대 기간을 고려해 합리적으로 정한다."},
    {"topic": "early_termination", "risk_level": "medium", "title": "중도해지 중개보수 전가", "raw_text": "임차인이 중도해지하는 경우 새 임차인 중개수수료 전액을 임차인이 부담한다.", "recommended_revision": "중개보수 부담은 중도해지 사유와 재임대 필요성에 따라 협의해 정한다."},
    {"topic": "early_termination", "risk_level": "high", "title": "임대인 일방 해지권", "raw_text": "임대인은 개인 사정이 있으면 언제든 계약을 해지할 수 있다.", "recommended_revision": "계약 해지는 법정 또는 합의된 사유가 있는 경우에 한정한다."},
    {"topic": "lease_period", "risk_level": "medium", "title": "기간 불명확", "raw_text": "임대차기간은 입주일부터 적당한 기간으로 한다.", "recommended_revision": "임대차 시작일과 종료일을 구체적인 날짜로 기재한다."},
    {"topic": "lease_period", "risk_level": "medium", "title": "종료일 선후 모순", "raw_text": "입주일은 2025년 11월 2일이고 계약 종료일은 2025년 11월 1일로 한다.", "recommended_revision": "입주일과 종료일의 선후관계가 맞도록 기간을 정정한다."},
    {"topic": "renewal", "risk_level": "high", "title": "갱신요구권 포기", "raw_text": "임차인은 계약갱신요구권을 행사하지 않기로 한다.", "recommended_revision": "계약갱신요구권 등 법정 권리는 법령에 따라 행사할 수 있음을 확인한다."},
    {"topic": "renewal", "risk_level": "medium", "title": "갱신 시 임대료 임의 인상", "raw_text": "갱신 시 보증금과 월세는 임대인이 정하는 금액으로 인상한다.", "recommended_revision": "갱신 시 차임 증감은 법령상 한도와 협의 절차를 따른다."},
    {"topic": "broker_duty", "risk_level": "medium", "title": "중개대상물 설명 면책", "raw_text": "중개대상물 확인·설명서의 내용과 실제 상태가 달라도 임대인과 중개사는 책임지지 않는다.", "recommended_revision": "확인·설명서와 실제 상태가 다르면 책임 소재와 시정 절차를 정한다."},
    {"topic": "broker_duty", "risk_level": "medium", "title": "등기부 미확인 면책", "raw_text": "중개사는 등기부 권리관계를 확인하지 않으며 임차인이 직접 확인한다.", "recommended_revision": "중개사는 중개대상물의 권리관계를 확인·설명하고 관련 자료를 제공한다."},
    {"topic": "identity_and_authority", "risk_level": "high", "title": "대리권 미확인", "raw_text": "대리인이 계약하는 경우 위임장과 인감증명서는 생략한다.", "recommended_revision": "대리 계약 시 위임장, 인감증명서, 신분증 및 임대인 의사를 확인한다."},
    {"topic": "identity_and_authority", "risk_level": "high", "title": "소유자 불일치 용인", "raw_text": "계약서상 임대인과 등기부상 소유자가 달라도 임차인은 문제 삼지 않는다.", "recommended_revision": "임대인과 소유자가 다르면 권한 증빙과 임대인 본인 확인을 거친다."},
    {"topic": "identity_and_authority", "risk_level": "medium", "title": "신분확인 생략", "raw_text": "계약 당사자는 신분증 확인 없이 서명만으로 본인 확인을 갈음한다.", "recommended_revision": "계약 당사자의 신분증과 등기부상 권한을 확인한다."},
    {"topic": "move_in_and_possession", "risk_level": "medium", "title": "인도 지연 면책", "raw_text": "임대인은 사정에 따라 주택 인도를 지연할 수 있고 임차인은 손해배상을 청구하지 않는다.", "recommended_revision": "인도 지연 시 해제권, 손해배상, 대체 거주 비용 등을 협의한다."},
    {"topic": "move_in_and_possession", "risk_level": "medium", "title": "열쇠 인도 불명확", "raw_text": "열쇠와 출입 권한은 임대인이 적절한 시기에 제공한다.", "recommended_revision": "열쇠, 공동현관 출입권한, 주차권 등의 인도일을 명확히 정한다."},
    {"topic": "sublease_and_transfer", "risk_level": "medium", "title": "전대 포괄 허용", "raw_text": "임차인은 임대인 동의 없이 전대하거나 임차권을 양도할 수 있다.", "recommended_revision": "전대와 임차권 양도는 임대인의 사전 서면 동의를 받도록 한다."},
    {"topic": "sublease_and_transfer", "risk_level": "medium", "title": "동거인 제한 과도", "raw_text": "임차인은 가족을 포함한 누구도 함께 거주하게 할 수 없다.", "recommended_revision": "거주 인원 제한은 주택 용도와 관리상 필요한 합리적 범위에서 정한다."},
    {"topic": "tax_and_arrears", "risk_level": "high", "title": "체납정보 확인 포기", "raw_text": "임차인은 임대인의 국세·지방세 체납 여부 확인을 요구하지 않는다.", "recommended_revision": "임차인은 임대인의 체납정보 및 선순위 권리관계를 확인할 수 있다."},
    {"topic": "tax_and_arrears", "risk_level": "medium", "title": "공과금 체납 인수", "raw_text": "입주 전 발생한 관리비, 수도, 전기, 가스 체납액은 임차인이 부담한다.", "recommended_revision": "입주 전 발생한 공과금과 관리비는 임대인이 정산한다."},
    {"topic": "special_clause", "risk_level": "medium", "title": "구두 합의 우선", "raw_text": "계약서와 다른 구두 합의가 있으면 구두 합의를 우선한다.", "recommended_revision": "계약 변경은 서면 합의로만 효력이 있음을 명시한다."},
    {"topic": "special_clause", "risk_level": "medium", "title": "임대인 면책 포괄", "raw_text": "본 계약과 관련한 모든 문제에 대해 임대인은 책임을 지지 않는다.", "recommended_revision": "책임 면제는 법령상 허용되는 범위와 구체적 사유로 한정한다."},
    {"topic": "special_clause", "risk_level": "medium", "title": "분쟁 관할 과도", "raw_text": "분쟁 발생 시 임대인이 지정하는 법원을 관할로 한다.", "recommended_revision": "관할은 민사소송법상 관할 또는 당사자에게 과도하지 않은 합의 관할로 정한다."},
    {"topic": "special_clause", "risk_level": "medium", "title": "일방 통지 효력", "raw_text": "임대인이 문자로 통지하면 임차인이 확인하지 않아도 모든 통지가 도달한 것으로 본다.", "recommended_revision": "중요 통지는 도달 확인 가능한 방식으로 하고 주소 변경 통지 의무를 함께 둔다."},
    {"topic": "pet", "risk_level": "medium", "title": "반려동물 위약금 과다", "raw_text": "반려동물 사육 사실이 발견되면 임차인은 즉시 보증금 전액을 위약금으로 포기한다.", "recommended_revision": "반려동물 관련 위약금은 실제 손해와 청소·복구 비용 범위에서 정한다."},
    {"topic": "pet", "risk_level": "low", "title": "반려동물 책임 범위 불명확", "raw_text": "반려동물로 인한 문제는 임차인이 책임진다.", "recommended_revision": "반려동물로 인한 구체적 훼손, 소음, 청소 책임 범위를 명확히 정한다."},
    {"topic": "option_and_fixture", "risk_level": "medium", "title": "옵션 고장 책임 전가", "raw_text": "냉장고, 세탁기, 에어컨 등 옵션 고장은 사용 기간과 무관하게 임차인이 수리한다.", "recommended_revision": "옵션의 노후 고장은 임대인이, 임차인의 고의·과실 훼손은 임차인이 부담한다."},
    {"topic": "option_and_fixture", "risk_level": "medium", "title": "옵션 목록 미기재", "raw_text": "옵션 물품은 현 상태대로 사용한다.", "recommended_revision": "옵션 목록, 상태, 고장 시 수리 책임을 별도 목록으로 첨부한다."},
    {"topic": "access_and_privacy", "risk_level": "high", "title": "임대인 자유 출입", "raw_text": "임대인은 필요 시 임차인의 동의 없이 주택에 출입할 수 있다.", "recommended_revision": "임대인의 출입은 긴급상황을 제외하고 사전 통지와 임차인의 동의를 거친다."},
    {"topic": "access_and_privacy", "risk_level": "medium", "title": "퇴거 전 상시 집보기", "raw_text": "계약 종료 3개월 전부터 임대인은 언제든 새 임차인에게 집을 보여줄 수 있다.", "recommended_revision": "집보기는 사전 협의한 일정과 합리적 시간대에 진행한다."},
    {"topic": "insurance_and_guarantee", "risk_level": "medium", "title": "보증보험 가입 제한", "raw_text": "임차인은 임대인의 동의 없이 전세보증금 반환보증에 가입할 수 없다.", "recommended_revision": "임차인은 필요 시 보증보험 가입을 신청할 수 있고 임대인은 필요한 협조를 한다."},
    {"topic": "insurance_and_guarantee", "risk_level": "medium", "title": "보증보험 비용 전가", "raw_text": "보증보험 가입에 필요한 모든 비용과 임대인 서류 발급 비용은 임차인이 부담한다.", "recommended_revision": "보증보험 비용 부담과 서류 협조 범위를 사전에 합리적으로 정한다."},
    {"topic": "sale_and_transfer", "risk_level": "medium", "title": "매매 시 임차인 권리 제한", "raw_text": "임대인이 주택을 매도하면 임차인은 매수인에게 대항하지 않는다.", "recommended_revision": "임차인의 대항력과 임대차 승계는 법령에 따른다."},
    {"topic": "sale_and_transfer", "risk_level": "medium", "title": "소유권 이전 통지 생략", "raw_text": "주택 소유권이 이전되어도 임대인은 임차인에게 통지하지 않을 수 있다.", "recommended_revision": "소유권 이전 또는 임대인 지위 승계가 있으면 즉시 임차인에게 통지한다."},
    {"topic": "deposit_return", "risk_level": "medium", "title": "보증금 공제 사유 포괄", "raw_text": "임대인은 필요하다고 판단하는 금액을 보증금에서 공제할 수 있다.", "recommended_revision": "보증금 공제는 미납 차임, 공과금, 입증된 손해 등 구체적 항목으로 한정한다."},
    {"topic": "deposit_return", "risk_level": "medium", "title": "손해액 산정 임대인 단독", "raw_text": "임대인이 산정한 손해액은 임차인이 다투지 않는다.", "recommended_revision": "손해액은 사진, 견적서, 영수증 등 객관 자료를 기준으로 협의한다."},
    {"topic": "repair_and_defect", "risk_level": "medium", "title": "하자 통지 기한 과도", "raw_text": "입주 후 24시간 이내 신고하지 않은 하자는 모두 임차인 책임으로 본다.", "recommended_revision": "입주 초기 점검 기간을 합리적으로 두고 숨은 하자는 발견 즉시 통지한다."},
    {"topic": "payment_structure", "risk_level": "medium", "title": "보증금 분할 구조 불명확", "raw_text": "계약금과 잔금 외 나머지 보증금은 추후 협의한다.", "recommended_revision": "보증금 총액, 계약금, 중도금, 잔금과 지급일을 모두 명확히 적는다."},
    {"topic": "payment_structure", "risk_level": "medium", "title": "영수인 불명확", "raw_text": "계약금은 임대인 외 제3자에게 지급할 수 있다.", "recommended_revision": "계약금 수령 권한, 계좌 명의, 영수증 발급 주체를 명확히 확인한다."},
    {"topic": "broker_duty", "risk_level": "medium", "title": "중개보수 초과 합의", "raw_text": "임차인은 법정 한도를 초과하는 중개보수를 지급하는 데 동의한다.", "recommended_revision": "중개보수는 법정 요율과 실제 거래금액 기준으로 산정한다."},
    {"topic": "broker_duty", "risk_level": "medium", "title": "중개사 책임 포괄 면제", "raw_text": "중개사는 본 계약과 관련한 어떠한 손해도 책임지지 않는다.", "recommended_revision": "중개사의 고의·과실 또는 확인·설명 의무 위반 책임은 면제하지 않는다."},
    {"topic": "priority_protection", "risk_level": "high", "title": "전세권 설정 거부 고정", "raw_text": "임차인은 전세권 설정, 임차권등기명령, 보증보험 등 보증금 보호 조치를 요구하지 않는다.", "recommended_revision": "보증금 보호 조치는 법령과 당사자 협의에 따라 진행할 수 있다."},
]


def normalize_space(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def deep_find_list(obj: Any, target_key: str) -> list[Any]:
    found: list[Any] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == target_key:
                    found.append(value)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(obj)
    return found


def normalize_to_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def save_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def create_session(max_retries: int) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=max_retries,
        connect=max_retries,
        read=max_retries,
        status=max_retries,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=1, pool_maxsize=1)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(
        {
            "User-Agent": "safelease-rag-seed/1.0 (+tenant-protection legal extraction)",
            "Accept": "application/json, text/plain, */*",
            "Connection": "close",
        }
    )
    return session


def api_get(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    timeout: int,
    sleep_sec: float,
    max_retries: int,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = session.get(url, params=params, timeout=timeout)
            if response.status_code in {429, 500, 502, 503, 504}:
                time.sleep(max(sleep_sec, 0.2) * attempt)
                continue
            response.raise_for_status()
            if sleep_sec:
                time.sleep(sleep_sec)
            return response.json()
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            http.client.RemoteDisconnected,
        ) as exc:
            last_error = exc
            time.sleep(max(sleep_sec, 0.2) * attempt)
    raise RuntimeError(f"API request failed: {url} params={params} error={last_error}")


def parse_search_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for key in ["law", "Law", "법령", "laws"]:
        for value in deep_find_list(payload, key):
            for item in normalize_to_list(value):
                if isinstance(item, dict):
                    items.append(item)
    return items


def find_law_id(
    session: requests.Session,
    oc: str,
    law_name: str,
    timeout: int,
    sleep_sec: float,
    max_retries: int,
) -> tuple[str, dict[str, Any]]:
    payload = api_get(
        session,
        BASE_SEARCH_URL,
        {
            "OC": oc,
            "target": "eflaw",
            "type": "JSON",
            "query": law_name,
            "search": 1,
            "display": 20,
            "page": 1,
            "sort": "lasc",
            "nw": "3",
        },
        timeout,
        sleep_sec,
        max_retries,
    )
    for item in parse_search_results(payload):
        name = normalize_space(item.get("법령명한글") or item.get("법령명") or "")
        law_id = str(item.get("법령ID") or item.get("법령일련번호") or "")
        if name == law_name and law_id:
            return law_id, payload
    raise RuntimeError(f"법령을 찾지 못했습니다: {law_name}")


def extract_articles(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = []
    for key in ["조문", "조문단위", "조문내용", "조문정보"]:
        candidates.extend(deep_find_list(payload, key))

    rows = []
    for candidate in candidates:
        for article in normalize_to_list(candidate):
            if not isinstance(article, dict):
                continue
            article_no = article.get("조문번호")
            if article_no is None:
                continue
            rows.append(
                {
                    "article_no": int(article_no),
                    "article_branch_no": int(article.get("조문가지번호") or 0),
                    "title": normalize_space(article.get("조문제목")),
                    "article_text": normalize_space(article.get("조문내용")),
                    "hang_text": normalize_space(article.get("항내용")),
                    "ho_text": normalize_space(article.get("호내용")),
                    "mok_text": normalize_space(article.get("목내용")),
                    "reference": normalize_space(article.get("조문참고자료")),
                }
            )

    deduped = []
    seen = set()
    for row in rows:
        key = (row["article_no"], row["article_branch_no"], row["article_text"], row["hang_text"], row["ho_text"], row["mok_text"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def article_body(row: dict[str, Any]) -> str:
    parts = [row.get("article_text"), row.get("hang_text"), row.get("ho_text"), row.get("mok_text"), row.get("reference")]
    return normalize_space(" ".join(part for part in parts if part))


def infer_law_topic(title: str, text: str) -> tuple[str, str]:
    haystack = f"{title} {text}"
    for topic, subtopic, keywords in LAW_TOPIC_RULES:
        if any(keyword in haystack for keyword in keywords):
            return topic, subtopic
    return "general_guidance", "legal_basis"


def build_law_seed(
    oc: str,
    output_dir: Path,
    timeout: int,
    sleep_sec: float,
    max_retries: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    documents = []
    chunks = []
    raw_dir = output_dir / "raw"
    session = create_session(max_retries)
    for law_name, refs in CORE_REFS.items():
        law_id, search_payload = find_law_id(session, oc, law_name, timeout, sleep_sec, max_retries)
        detail_payload = api_get(
            session,
            BASE_SERVICE_URL,
            {"OC": oc, "target": "eflaw", "type": "JSON", "ID": law_id},
            timeout,
            sleep_sec,
            max_retries,
        )
        save_json(raw_dir / f"search_{law_name}.json", search_payload)
        save_json(raw_dir / f"detail_{law_name}.json", detail_payload)

        document_id = f"law_seed::{law_id}"
        documents.append(
            {
                "document_id": document_id,
                "source_type": "law",
                "source_name": law_name,
                "title": law_name,
                "raw_text": f"{law_name} 핵심 조문",
                "normalized_text": f"{law_name} 핵심 조문",
                "metadata_json": {"law_id": law_id, "seed": "rag_seed"},
            }
        )
        articles = {(row["article_no"], row["article_branch_no"]): row for row in extract_articles(detail_payload)}
        for article_no, branch_no in refs:
            row = articles.get((article_no, branch_no))
            if not row:
                continue
            title = f"{law_name} 제{article_no}조" + (f"의{branch_no}" if branch_no else "")
            if row.get("title"):
                title += f" {row['title']}"
            body = article_body(row)
            if not body:
                continue
            topic, subtopic = infer_law_topic(title, body)
            uid = f"{law_id}:{article_no:04d}:{branch_no:02d}"
            chunks.append(
                {
                    "chunk_id": f"law_seed::{uid}",
                    "document_id": document_id,
                    "source_type": "law",
                    "source_name": law_name,
                    "title": title,
                    "chunk_text": body,
                    "normalized_text": body,
                    "embedding_text": f"{title}\n{body}",
                    "topic": topic,
                    "subtopic": subtopic,
                    "reliability": "primary",
                    "audience": "tenant",
                    "law_name": law_name,
                    "law_id": law_id,
                    "article_uid": uid,
                    "article_no": article_no,
                    "article_branch_no": branch_no,
                    "is_primary_authority": True,
                    "metadata_json": {"seed": "rag_seed", "article_title": row.get("title")},
                }
            )
    return documents, chunks


def build_clause_seed() -> list[dict[str, Any]]:
    rows = []
    for index, clause in enumerate(TENANT_RISK_CLAUSES, start=1):
        raw_text = normalize_space(clause["raw_text"])
        recommended_revision = normalize_space(clause["recommended_revision"])
        title = normalize_space(clause["title"])
        topic = clause["topic"]
        rows.append(
            {
                "library_clause_id": f"tenant_risk_{index:03d}_{hashlib.sha1(raw_text.encode('utf-8')).hexdigest()[:8]}",
                "source_chunk_id": None,
                "source_type": "tenant_risk_seed",
                "source_name": "SafeLease",
                "title": title,
                "raw_text": raw_text,
                "normalized_text": raw_text,
                "topic": topic,
                "label_type": "risk_clause",
                "perspective": "tenant",
                "favorability": "unfavorable",
                "risk_level": clause["risk_level"],
                "legality_status": "needs_review",
                "embedding_text": f"{title}\n위험 특약: {raw_text}\n권장 수정: {recommended_revision}\n주제: {topic}",
                "metadata_json": {
                    "recommended_revision": recommended_revision,
                    "seed": "rag_seed",
                    "tenant_protection": True,
                },
            }
        )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--oc", default=os.getenv("LAW_API_OC", ""))
    parser.add_argument("--skip-law-api", action="store_true")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--sleep-sec", type=float, default=0.2)
    parser.add_argument("--max-retries", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    documents: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    if not args.skip_law_api:
        if not args.oc:
            raise ValueError("LAW_API_OC 또는 --oc가 필요합니다.")
        documents, chunks = build_law_seed(args.oc, output_dir, args.timeout, args.sleep_sec, args.max_retries)

    clauses = build_clause_seed()
    save_jsonl(output_dir / "source_documents.jsonl", documents)
    save_jsonl(output_dir / "source_chunks.jsonl", chunks)
    save_jsonl(output_dir / "tenant_risk_clauses.jsonl", clauses)
    manifest = {
        "source_documents": len(documents),
        "source_chunks": len(chunks),
        "tenant_risk_clauses": len(clauses),
        "output_dir": str(output_dir.resolve()),
    }
    save_json(output_dir / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

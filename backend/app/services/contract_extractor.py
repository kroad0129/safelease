import json
import os
from pathlib import Path

from openai import OpenAI

from app.core.common import OUTPUT_DIR, ensure_output_dir, get_required_env, load_project_env, write_text
from app.core.progress import log_step


def get_openai_client() -> OpenAI:
    load_project_env()
    api_key = get_required_env("OPENAI_API_KEY")
    return OpenAI(api_key=api_key)


def upload_file(path: str) -> str:
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = file_path.resolve()

    if not file_path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

    log_step(2, "OpenAI 파일 저장소에 PDF 업로드 중")
    client = get_openai_client()
    with open(file_path, "rb") as f:
        uploaded = client.files.create(
            file=f,
            purpose="user_data"
        )
    log_step(3, f"PDF 업로드 완료: file_id={uploaded.id}")
    return uploaded.id


def build_prompt() -> str:
    return """
첨부한 문서는 부동산 임대차 계약서다.
문서를 읽고 반드시 아래 스키마에 맞는 JSON 객체만 출력해.
설명, 코드블록, 마크다운 없이 JSON만 출력해.
첫 글자는 { 이고 마지막 글자는 } 여야 한다.
값이 없거나 확인할 수 없으면 null로 넣어.
절대 추측하지 마.

중요:
상단의 전세/월세는 체크박스를 보고 판단해야 한다.
문서에 '□ 전세 □ 월세'처럼 둘 다 체크되지 않았으면 lease_type은 반드시 null로 넣어.
차임, 보증금, 본문 문맥만으로 월세/전세를 추론하지 마.
체크된 표시가 명확할 때만 "전세" 또는 "월세"를 넣어.

중요 규칙:
1) 모든 주요 필드는 가능한 한 raw_text 원문을 함께 가져와라.
문서에 적힌 원문이 있으면 raw_text에 그대로 넣어라.
원문에 띄어쓰기, 괄호, 기호가 있으면 raw_text에는 그대로 유지해라.

2) 금액 관련 필드는 다음을 모두 추출해.
- raw_text: 문서에 적힌 해당 금액 전체 원문
- korean_text: 한글 금액 표현만 추출
- numeric_text: 숫자/통화기호 금액 표현만 추출
- normalized_value: 숫자형 정수로 정규화한 값

예:
"금오백만원정 (₩5,000,000)" 이면
{
  "raw_text": "금오백만원정 (₩5,000,000)",
  "korean_text": "금오백만원정",
  "numeric_text": "₩5,000,000",
  "normalized_value": 5000000
}

금액이 한글만 있으면 korean_text만 채우고 numeric_text는 null.
금액이 숫자만 있으면 numeric_text만 채우고 korean_text는 null.
금액이 없으면 전부 null.

3) 날짜 관련 필드는 다음을 추출해.
- raw_text: 문서에 적힌 날짜 원문
- normalized_value: 가능하면 YYYY-MM-DD 형식
날짜가 빈칸 형식이어도 원문이 있으면 raw_text는 보존해라.
예: "년 월 일" -> raw_text는 "년 월 일", normalized_value는 null

4) 면적, 매월지불일도 raw_text와 normalized_value를 함께 추출해.
매월지불일의 normalized_value는 문자열이 아니라 숫자형으로 넣어라.
예: "20일" -> 20

5) 건물 구조/용도 값은 빠뜨리지 말고 반드시 추출해.
예: "철 근 콘 크 리 트" -> raw_text는 그대로, value는 정리된 값

6) 임대할부분은 반드시 원문과 함께 동/호를 분리해.
예:
"104동 1702호 전부" 라면
- raw_text: "104동 1702호 전부"
- dong: "104동"
- ho: "1702호"

전부/일부 같은 추가 표현이 있으면 raw_text에는 유지하고,
dong, ho에는 동/호만 분리해서 넣어.

7) payment는 보기 쉽게 아래 항목만 따로 모아서 추출해.
- 보증금
- 계약금
- 계약금 영수자
- 중도금
- 중도금 지불날짜
- 잔금
- 잔금 지불날짜
- 차임(월세)
- 선불/후불
- 매월지불날짜

rent_payment_type은 다음처럼 추출해라.
- raw_text: 원문 그대로. 예: "(선불로)"
- value: 정리된 값. 예: "선불"

8) contract_terms에는 제1조부터 문서에 존재하는 마지막 조항까지 모두 넣어.
각 조항은 다음 필드를 가져야 해.
- article_no
- content
- dates
- numbers

9) article_no는 원문 띄어쓰기와 상관없이 반드시 정규화해서 넣어라.
형식은 항상 다음처럼 통일:
- "제1조"
- "제2조"
- "제3조"

10) content에는 조항 번호를 넣지 마라.
즉 "제1조", "제2조" 같은 표현은 content에서 제거하고,
조항 제목과 본문만 넣어라.

예:
- article_no: "제1조"
- content: "(목적) 위 부동산의 임대차에 한하여 임대인과 임차인은 합의에 의하여 임차보증금 및 차임을 아래와 같이 지불하기로 한다."

11) content는 조항 전체 본문을 끝까지 넣어라.
조항 제목부터 시작해서 다음 조항 번호가 나오기 전까지의 모든 문장을 하나의 content에 넣어라.
줄바꿈 때문에 문장이 끊겨 보여도 같은 조항이면 이어서 합쳐라.

중요:
- content를 첫 문장까지만 자르지 마라.
- 쉼표(,)에서 자르지 마라.
- 줄바꿈이 있어도 같은 조항이면 이어서 추출해라.
- 다음 조항 번호(예: 제3조, 제4조) 또는 특약사항, 서명영역이 나오기 전까지는 모두 같은 조항 본문으로 본다.
- 따라서 제5조, 제7조, 제8조처럼 여러 문장으로 이루어진 조항은 뒤 문장까지 모두 포함해야 한다.

12) 제1조는 payment와 중복되는 정보가 많으므로,
제1조 안에 보증금, 계약금, 중도금, 잔금, 차임, 지급일 관련 정보가 있더라도
그것은 payment에서만 관리하고 contract_terms의 dates, numbers에는 넣지 마라.
즉 제1조의 dates와 numbers는 특별한 추가 정보가 없으면 빈 배열이어야 한다.

13) 다른 조항들도 dates, numbers는 정말 조항 자체의 추가 의미가 있을 때만 넣어라.
다음은 제외:
- 조 번호 자체
- 이미 별도 date 필드로 추출한 날짜
- 이미 상위 payment 필드로 추출한 금액
- 이미 monthly_due_day 같은 별도 필드로 추출한 숫자

14) contract_terms.numbers는 문자열 배열이 아니라 반드시 객체 배열로 넣어라.
형식:
{
  "raw_text": "...",
  "normalized_value": ...
}

예:
- "2회 이상" -> { "raw_text": "2회 이상", "normalized_value": 2 }
- "0.9%" -> { "raw_text": "0.9%", "normalized_value": 0.9 }

15) special_terms는 항목별 객체 배열로 넣어.
각 특약은 다음 필드를 가져야 해.
- order
- content
- dates
- numbers

special_terms.numbers도 contract_terms.numbers와 동일하게
문자열 배열이 아니라 객체 배열로 넣어라.

16) special_terms의 order는 숫자형으로 넣어라.
예: 1, 2

17) 계좌번호는 특약사항 각 항목 안에 넣지 말고,
문서 전체 특약사항 영역 기준으로 별도 최상위 필드 special_terms_account_numbers 배열에 넣어라.

예:
"special_terms_account_numbers": [
  {
    "raw_text": "110-123-123456",
    "value": "110-123-123456"
  }
]

계좌번호가 없으면 빈 배열 [] 로 넣어라.

18) 아래 항목은 특히 빠뜨리지 말고 최대한 정확히 추출해.
- property.address
- property.land.category
- property.land.area_m2
- property.building.structure_usage
- property.building.area_m2
- property.leased_part
- payment.deposit
- payment.monthly_rent
- lessor.address
- lessor.name
- lessee.address
- lessee.name
- broker.office_address
- broker.registration_number
- 문서 하단 계약체결일
- 말미의 계약 확인 문구

출력 스키마:
{
  "document_type": "real_estate_lease_contract",
  "lease_type": null,
  "contract_date": {
    "raw_text": null,
    "normalized_value": null
  },
  "contract_confirmation_text": null,
  "property": {
    "address": {
      "raw_text": null,
      "value": null
    },
    "land": {
      "category": {
        "raw_text": null,
        "value": null
      },
      "area_m2": {
        "raw_text": null,
        "normalized_value": null
      }
    },
    "building": {
      "structure_usage": {
        "raw_text": null,
        "value": null
      },
      "area_m2": {
        "raw_text": null,
        "normalized_value": null
      }
    },
    "leased_part": {
      "raw_text": null,
      "dong": null,
      "ho": null,
      "area_m2": {
        "raw_text": null,
        "normalized_value": null
      }
    }
  },
  "payment": {
    "deposit": {
      "raw_text": null,
      "korean_text": null,
      "numeric_text": null,
      "normalized_value": null
    },
    "contract_money": {
      "raw_text": null,
      "korean_text": null,
      "numeric_text": null,
      "normalized_value": null
    },
    "contract_money_received_by": {
      "raw_text": null,
      "value": null
    },
    "intermediate_money": {
      "raw_text": null,
      "korean_text": null,
      "numeric_text": null,
      "normalized_value": null
    },
    "intermediate_money_payment_date": {
      "raw_text": null,
      "normalized_value": null
    },
    "balance": {
      "raw_text": null,
      "korean_text": null,
      "numeric_text": null,
      "normalized_value": null
    },
    "balance_payment_date": {
      "raw_text": null,
      "normalized_value": null
    },
    "monthly_rent": {
      "raw_text": null,
      "korean_text": null,
      "numeric_text": null,
      "normalized_value": null
    },
    "rent_payment_type": {
      "raw_text": null,
      "value": null
    },
    "monthly_due_day": {
      "raw_text": null,
      "normalized_value": null
    }
  },
  "contract_terms": [
    {
      "article_no": null,
      "content": null,
      "dates": [],
      "numbers": [
        {
          "raw_text": null,
          "normalized_value": null
        }
      ]
    }
  ],
  "special_terms": [
    {
      "order": null,
      "content": null,
      "dates": [],
      "numbers": [
        {
          "raw_text": null,
          "normalized_value": null
        }
      ]
    }
  ],
  "special_terms_account_numbers": [],
  "lessor": {
    "address": {
      "raw_text": null,
      "value": null
    },
    "name": {
      "raw_text": null,
      "value": null
    },
    "resident_registration_number": {
      "raw_text": null,
      "value": null
    },
    "phone": {
      "raw_text": null,
      "value": null
    }
  },
  "lessee": {
    "address": {
      "raw_text": null,
      "value": null
    },
    "name": {
      "raw_text": null,
      "value": null
    },
    "resident_registration_number": {
      "raw_text": null,
      "value": null
    },
    "phone": {
      "raw_text": null,
      "value": null
    }
  },
  "broker": {
    "office_address": {
      "raw_text": null,
      "value": null
    },
    "registration_number": {
      "raw_text": null,
      "value": null
    },
    "office_name": {
      "raw_text": null,
      "value": null
    },
    "representative_name": {
      "raw_text": null,
      "value": null
    }
  }
}
"""


def extract_first_json_object(text: str) -> str:
    start = text.find("{")
    if start == -1:
        raise ValueError("응답에서 JSON 시작 문자 '{'를 찾지 못했습니다.")

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]

    raise ValueError("응답에서 JSON 객체의 끝을 찾지 못했습니다.")


def repair_json_text(json_text: str) -> str:
    json_text = json_text.strip()
    json_text = json_text.replace("```json", "").replace("```", "").strip()
    json_text = extract_first_json_object(json_text)

    result = []
    in_string = False
    escape = False
    valid_escapes = {'"', "\\", "/", "b", "f", "n", "r", "t", "u"}

    i = 0
    while i < len(json_text):
        ch = json_text[i]

        if in_string:
            if escape:
                result.append(ch)
                escape = False
            else:
                if ch == "\\":
                    next_ch = json_text[i + 1] if i + 1 < len(json_text) else ""
                    if next_ch not in valid_escapes:
                        result.append("\\")
                        result.append("\\")
                    else:
                        result.append("\\")
                        escape = True
                elif ch == '"':
                    result.append(ch)
                    in_string = False
                else:
                    result.append(ch)
        else:
            result.append(ch)
            if ch == '"':
                in_string = True

        i += 1

    return "".join(result)


def extract_contract_from_pdf(file_id: str) -> dict:
    prompt = build_prompt()
    client = get_openai_client()

    log_step(4, "OpenAI에 계약서 구조화 추출 요청 중")

    response = client.responses.create(
        model="gpt-5.4-mini",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "file_id": file_id
                    },
                    {
                        "type": "input_text",
                        "text": prompt
                    }
                ]
            }
        ]
    )

    result_text = response.output_text.strip()

    log_step(5, "모델 응답 수신 완료")
    log_step(6, "계약서 JSON 파싱 및 필요 시 복구 중")

    try:
        parsed = json.loads(result_text)
        log_step(7, "계약서 구조화 JSON 파싱 완료")
        return parsed
    except json.JSONDecodeError:
        repaired = repair_json_text(result_text)

        if os.getenv("SAFELEASE_DEBUG_EXTRACTION") == "1":
            ensure_output_dir()
            debug_dir = OUTPUT_DIR / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            write_text(debug_dir / "debug_raw_response.txt", result_text)
            write_text(debug_dir / "debug_repaired_response.json", repaired)

        parsed = json.loads(repaired)
        log_step(7, "계약서 구조화 JSON 복구 후 파싱 완료")
        return parsed

# SafeLease Backend README

SafeLease 백엔드는 주택 임대차 계약서 PDF를 업로드받아 계약 내용을 구조화하고, 주소/중개업/임대료를 검증한 뒤, 법령 RAG와 특약 분석을 붙여 임차인 보호 관점의 검토 결과를 생성한다. 프론트엔드는 현재 시각화용 임시 화면이며, 실제 핵심 로직은 이 백엔드에 있다.

## 전체 처리 흐름

1. `POST /api/contracts/verify`로 PDF 업로드
2. PDF를 OpenAI 파일 저장소에 업로드
3. `gpt-5.4-mini`로 계약서 구조화 JSON 추출
4. 추출 결과를 검증용 형태로 정규화
5. 목적물 주소와 동/층/호 상세주소 검증
6. 임대인/임차인 주소 검증
7. VWorld 중개업 조회로 중개사 등록번호, 상호, 소재지, 대표자 검증
8. 실거래 통계 DB로 환산월세 비교
9. 규칙 기반 finding 생성
10. RAG로 법령/가이드/특약 후보 검색
11. LLM이 계약조건과 특약을 분석
12. LLM 2차 검증으로 법령 근거를 `direct`, `supporting`, `irrelevant`로 필터링
13. PDF 하이라이트, PNG 미리보기, JSON 산출물 저장
14. 분석 결과 기반 챗봇에서 질의응답과 특약 추천 제공

## 실행 진입점

### `app/api.py`

FastAPI 서버 진입점이다.

- `GET /health`
  - 서버 상태 확인용.
- `POST /api/contracts/verify`
  - PDF 파일만 허용한다.
  - 빈 파일이면 400 에러를 반환한다.
  - 내부적으로 `verify_contract_upload_stream()`을 호출한다.
  - 최종 응답은 `presenters/verify_response.py`에서 프론트용 payload로 변환한다.
- `POST /api/contracts/chat`
  - 분석 완료 후 생성된 `/outputs/.../combined_result.json`을 기반으로 질문에 답한다.
  - 예: “유리한 특약 추천해줘”, “반려동물 키울 때 도움이 되는 특약 있어?”, “이 조항 왜 위험해?”

현재는 이전의 진행률 폴링 API(`/verify-jobs`)를 제거했고, 단일 요청으로 검증이 끝나는 구조다.

### `main.py`

CLI 실행용 래퍼다.

```bash
python main.py sample.pdf
```

내부적으로 `app.cli.main()`을 실행한다.

### `run_backend_check.py`

간단한 백엔드 smoke check용 스크립트다. PDF 경로를 받거나 `sample.pdf`를 사용해서 전체 검증 파이프라인을 실행하고 핵심 산출물 경로만 JSON으로 출력한다.

## 공통 모듈

### `app/core/common.py`

프로젝트 공통 상수와 유틸리티를 둔다.

- `PROJECT_ROOT`: `backend/` 폴더
- `OUTPUT_DIR`: `backend/outputs`
- `SAMPLE_PDF_PATH`: `backend/sample.pdf`
- `ENV_PATH`: `backend/.env`
- `load_project_env()`: `.env` 로드
- `get_required_env(name)`: 필수 환경변수 조회
- `ensure_output_dir()`: `outputs/` 생성
- `save_json(path, data)`: UTF-8 JSON 저장
- `write_text(path, content)`: 텍스트 저장
- `build_result(...)`: 외부 검증 결과 표준 포맷 생성

`build_result()`의 공통 형태:

```json
{
  "status": "success | not_found | partial_match | query_failed",
  "data": {},
  "error_code": null,
  "error_message": null,
  "debug": {}
}
```

### `app/core/progress.py`

서버/CLI 로그용 단계 출력 모듈이다. 예전에는 프론트 진행률 폴링과 연결됐지만, 지금은 단순 로그만 담당한다.

- 총 단계 수: `TOTAL_STEPS = 18`
- `log_step(step, message)`:
  - `[01/18] 10:00:00 (+0ms, total 0ms) 계약서 검증 시작` 형태로 출력한다.
  - 단계별 elapsed time과 total elapsed time을 같이 보여준다.

## 계약서 추출/검증 파이프라인

### `app/services/contract_service.py`

업로드 파일 또는 로컬 PDF 경로를 검증 파이프라인으로 연결하는 얇은 서비스다.

- `verify_contract_path(pdf_path)`
  - `contract_verifier.verify_contract_pdf()`로 추출/검증 실행
  - `verification_persistence.persist_verification_outputs()`로 산출물 저장
- `verify_contract_upload_stream(filename, file_obj)`
  - 업로드 스트림을 임시 PDF로 저장
  - 검증 완료 후 임시 파일 삭제

### `app/services/contract_extractor.py`

OpenAI를 사용해 PDF 계약서를 구조화 JSON으로 추출한다.

핵심 함수:

- `upload_file(path)`
  - PDF를 OpenAI 파일 저장소에 업로드한다.
  - `purpose="user_data"`를 사용한다.
- `build_prompt()`
  - 계약서 추출 지시문과 출력 스키마를 만든다.
- `extract_contract_from_pdf(file_id)`
  - `gpt-5.4-mini`에 PDF 파일과 프롬프트를 전달한다.
  - 결과는 반드시 JSON 객체여야 한다.
  - JSON 파싱 실패 시 `repair_json_text()`로 코드블록 제거, 첫 JSON 객체 추출, 잘못된 escape 보정 후 재파싱한다.

중요 추출 정책:

- 전세/월세는 문서 상단 체크박스로만 판단한다.
  - `□ 전세 □ 월세`처럼 둘 다 체크되지 않았으면 `lease_type = null`
  - 보증금/차임 문맥만으로 월세/전세를 추론하지 않는다.
- 금액 필드는 `raw_text`, `korean_text`, `numeric_text`, `normalized_value`를 모두 추출한다.
- 날짜 필드는 `raw_text`, `normalized_value(YYYY-MM-DD 가능 시)`를 모두 추출한다.
- `contract_terms`는 제1조부터 마지막 조항까지 유지한다.
- 제1조의 보증금/차임 정보는 `payment`에만 관리하고, 제1조 `dates`, `numbers`에는 중복으로 넣지 않도록 지시한다.
- `special_terms_account_numbers`는 특약 본문과 분리해 별도 최상위 배열로 둔다.

디버그:

- 기본적으로 LLM 원문 응답을 파일로 저장하지 않는다.
- `SAFELEASE_DEBUG_EXTRACTION=1`일 때만 `outputs/debug/debug_raw_response.txt`, `debug_repaired_response.json`을 저장한다.

### `app/services/contract_normalizer.py`

LLM 추출 결과를 외부 검증에 쓰기 쉬운 얇은 형태로 정리한다.

- 목적물 주소, 임대할 부분, 면적
- 보증금, 월세
- 임대인/임차인 주소와 이름
- 중개업 등록번호, 소재지, 상호, 대표자명
- 중개업 소재지에서 `sido`, `sigungu`를 추출해 VWorld 조회 입력으로 사용

예:

```json
{
  "property": {
    "address": "서울시 강서구 화곡동 1052-14",
    "leased_part_raw": "5층 503호 전부",
    "area_m2": 29.6
  },
  "payment": {
    "deposit": 20000000,
    "monthly_rent": 750000
  }
}
```

### `app/services/contract_verifier.py`

추출된 계약서를 실제 검증 서비스들과 연결하는 오케스트레이터다.

처리 단계:

1. PDF 업로드
2. 계약서 JSON 추출
3. 검증 입력 정규화
4. 목적물 주소 및 동/층/호 상세주소 검증
5. 임대인/임차인 주소 검증
6. 중개업 등록번호 조회
7. 임대료 참고 시세 비교
8. `verification_analysis.build_analysis()`로 finding 생성

중개업 조회는 `sido`, `sigungu`, `registration_number`가 모두 있을 때만 실행한다. 부족하면 `BROKER_INPUT_MISSING` 결과를 만든다.

### `app/services/verification_analysis.py`

주소/중개사/임대료 검증 결과를 사람이 읽을 수 있는 finding으로 바꾼다.

판정 레벨:

- `error` → `주의`
- `warning` → `보통`
- `info` → `양호`

주요 finding:

- 주소 누락
- 목적물 기본주소 조회 실패
- 동/층/호 상세주소 불일치
- 임대인/임차인 주소 조회 실패
- 중개업 등록번호 누락
- 중개업 등록번호/대표자/상호/소재지 불일치
- 환산월세가 참고 범위 초과

전체 요약:

- error가 1개 이상이면 `overall_status = fail`, `review_level = 주의`
- warning만 있으면 `overall_status = warning`, `review_level = 보통`
- finding이 없으면 `overall_status = pass`, `review_level = 양호`

## 외부 검증

### `app/validators/address_validator.py`

도로명주소 API로 주소와 상세주소를 확인한다.

환경변수:

- `JUSO_ROAD_API_KEY`
- `JUSO_DETAIL_API_KEY`

사용 API:

- 도로명주소 검색: `https://business.juso.go.kr/addrlink/addrLinkApi.do`
- 상세주소 검색: `https://business.juso.go.kr/addrlink/addrDetailApi.do`

처리 방식:

1. `base_address`로 도로명주소 검색
2. `leased_part`에서 동/층/호 추출
   - 예: `104동 1702호 전부` → `dong=104동`, `ho=1702호`
   - 예: `5층 503호 전부` → `floor=5층`, `ho=503호`
3. 기본주소가 확인되고 동/층/호가 있으면 상세주소 API로 목록 조회
4. 입력 동/층/호와 API 목록을 비교

결과 상태:

- `success`: 기본주소 확인, 필요 시 상세주소도 일치
- `not_found`: 주소 또는 상세주소가 없음
- `partial_match`: 기본주소는 있지만 상세주소 목록 확인이 불가능
- `query_failed`: API 오류 또는 파싱 실패

### `app/validators/broker_validator.py`

VWorld 부동산중개업 조회 페이지를 Selenium으로 조회한다.

조회 대상:

- 시도
- 시군구
- 중개업 등록번호

반환 데이터:

- 등록번호
- 상호
- 사무소 소재지
- 대표자명
- 등록일
- 상태
- 업무 시작/종료일

특징:

- Chrome headless 모드 사용
- DOM 로딩 불안정성을 고려해 최대 3회 재시도
- 시도/시군구 select box 로딩, 등록번호 입력, `fnSearch()` 실행, 결과 테이블 파싱 순서로 동작

## 임대료 참고 시세 비교

### `app/services/rent_reference_service.py`

계약서의 보증금과 월세를 `환산월세`로 바꿔 DB의 참고 통계와 비교한다.

기본 전월세전환율:

```python
DEFAULT_CONVERSION_RATE = 0.045
```

환산월세 공식:

```text
환산월세(만원) = 월세금(만원) + 보증금(만원) * 0.045 / 12
```

예:

- 보증금 20,000,000원 = 2,000만원
- 월세 750,000원 = 75만원
- 환산월세 = 75 + 2,000 * 0.045 / 12 = 82.5만원

면적 구간:

- `< 20㎡`: `lt_20`
- `20㎡ 이상~30㎡ 미만`: `gte_20_lt_30`
- `30㎡ 이상~40㎡ 미만`: `gte_30_lt_40`
- `40㎡ 이상~50㎡ 미만`: `gte_40_lt_50`
- `50㎡ 이상~60㎡ 미만`: `gte_50_lt_60`
- `60㎡ 이상~85㎡ 미만`: `gte_60_lt_85`
- `85㎡ 이상`: `gte_85`

통계 선택 우선순위:

1. `dong_area`: 법정동 + 면적구간
2. `area`: 시군구 + 면적구간
3. `dong`: 법정동 전체
4. `region`: 시군구 전체

단, `dong_area`는 표본 수가 `MIN_DONG_AREA_SAMPLE = 10` 이상일 때만 직접 사용한다. 표본이 적으면 fallback으로 `area`, `dong`, `region` 순서로 내려간다.

신뢰도:

- `sample_count >= 30` → `confidence = strong`
- `sample_count < 30` → `confidence = weak`

비교 기준:

- 계약 환산월세가 P90 초과 → `status = high`, warning
- 계약 환산월세가 P75 초과 → `status = slightly_high`, warning
- 계약 환산월세가 P25 미만 → `status = low`, info
- P25~P75 범위 → `status = normal`, info

사용 DB 테이블:

- `rent_reference_stats`
  - `basis`
  - `sgg_cd`
  - `legal_dong_cd`
  - `umd_nm`
  - `area_band`
  - `sample_count`
  - `p25_converted_monthly_rent`
  - `p75_converted_monthly_rent`
  - `median_converted_monthly_rent`
  - `p90_converted_monthly_rent`
  - `median_deposit_manwon`
  - `median_monthly_rent_wolse_only`
  - `median_area_m2`

## RAG 법령/특약 분석

### `app/services/rag_analysis_service.py`

계약조건과 특약을 법령, 가이드, 유사 특약 라이브러리와 비교하고 LLM 분석 결과를 만든다.

기본 모델:

```python
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_ANALYSIS_MODEL = "gpt-5.4-mini"
```

검색 개수와 유사도 기준:

```python
LEGAL_FETCH_K = 12
GUIDE_FETCH_K = 12
CLAUSE_FETCH_K = 8

LEGAL_MIN_SIMILARITY = 0.4
GUIDE_MIN_SIMILARITY = 0.4
CLAUSE_MIN_SIMILARITY = 0.4
```

사용 DB 테이블:

- `source_documents`
  - 법령, 가이드 문서 원본 메타데이터
- `source_chunks`
  - 법령 조문/가이드 문단 청크
  - `source_type`, `source_name`, `topic`, `law_name`, `article_no`, `article_branch_no`
- `source_chunk_embeddings`
  - `source_chunks`의 벡터
- `clause_library`
  - 위험 특약, 유사 특약 라이브러리
  - `favorability`, `risk_level`, `legality_status`
- `clause_library_embeddings`
  - 특약 라이브러리 벡터

분석 query item:

- 계약조건
  - 보증금 조건
  - 잔금 조건
  - 월 차임 조건
  - 차임 지급 방식
  - 임대차 기간 조건
  - 목적물 표시
- 진단성 항목
  - 전세/월세 유형 확인: 체크박스가 불명확하면 생성
  - 보증금 합계 확인: 계약금 + 중도금 + 잔금 합계가 보증금과 다르면 생성
  - 잔금 구조 확인: 잔금이 보증금보다 크면 생성
  - 임대차 기간 확인: 인도일보다 종료일이 빠르면 생성
  - 중도금 기재 확인: 원문 흔적은 있는데 금액 정규화가 실패하면 생성
- 특약
  - `special_terms` 각 항목별로 `특약 1`, `특약 2`처럼 query 생성

토픽 체계:

- `deposit_return`
- `priority_protection`
- `rent_increase`
- `renewal`
- `broker_duty`
- `management_fee`
- `access_and_privacy`
- `insurance_and_guarantee`
- `sale_and_transfer`
- `option_and_fixture`
- `pet`
- `move_in_and_possession`
- `restoration`
- `deposit_protection`
- `repair_and_defect`
- `registry_and_rights`
- `identity_and_authority`
- `contract_basics`
- `special_clause`
- `broker_and_fee`
- `sublease_and_transfer`

검색 흐름:

1. query text를 embedding
2. `source_chunk_embeddings`에서 법령/가이드 후보 검색
3. `clause_library_embeddings`에서 특약 후보 검색
4. topic 일치, 일반 가이드, 법령 선호 조문, 토큰 겹침 등을 반영해 rerank
5. LLM payload에 법령 3개, 가이드 3개, 유사 특약 2개 정도로 압축

법령 선호 조문 예:

- 차임/월세: 민법 제633조, 주택임대차보호법 제7조, 제10조
- 보증금/계약금/잔금: 주택임대차보호법 제10조, 민법 제565조
- 기간: 민법 제623조, 주택임대차보호법 제4조
- 하자/수리: 민법 제623조, 제634조, 주택임대차보호법 제10조
- 중개/설명서: 공인중개사법 제25조, 공인중개사법 시행규칙 제16조
- 전입/확정일자/선순위: 주택임대차보호법 제3조, 제10조

LLM 분석 원칙:

- 법령 위반/무효 단정은 `legal_evidence`를 우선한다.
- `guidance_evidence`만 있으면 “주의 필요”, “분쟁 소지”, “실무상 점검 필요” 정도로 표현한다.
- 특약은 임차인 관점에서 유리/불리/중립을 판단한다.
- 월 차임 금액이나 지급 방식은 보증금 일부를 월세로 전환했다는 명시가 없으면 전월세전환율만으로 주의 처리하지 않는다.

2차 법령 검증:

1. 1차 LLM 분석 결과의 `legal_basis` 후보를 모은다.
2. 후보 조문 전문/제목/분석 이유를 다시 LLM에 전달한다.
3. 각 후보를 다음으로 분류한다.
   - `direct`: 판단을 직접 뒷받침
   - `supporting`: 배경 또는 간접 참고
   - `irrelevant`: 해당 분석 근거로 부적절
4. `irrelevant`는 최종 `legal_basis`에서 제거한다.
5. 남은 조문은 `legal_basis_details`에 조문 내용까지 포함된다.

저장 파일:

- `rag_result.json`: 검색 결과 원본
- `rag_llm_payload.json`: LLM 분석 입력
- `rag_analysis_result.json`: 최종 분석 결과

### `app/services/rag_contract_rules.py`

RAG 분석 결과와 하이라이트 위치를 연결하기 위한 규칙 모음이다.

예:

- `보증금 조건` → `payment.deposit`
- `잔금 조건` → `payment.balance`
- `월 차임 조건` → `payment.monthly_rent`
- `차임 지급 방식` → `payment.monthly_due_day`
- `임대차 기간 조건` → `contract_terms[article_no=제2조].content`
- `특약 분석`은 `special_terms[index].content`

또한 LLM judgment 문구를 기반으로 review level을 보정한다.

- “불리”, “주의”, “위험”, “불명확”, “분쟁” → `주의`
- “중립”, “보통”, “확인 권장” → `보통`
- “유리”, “양호”, “무난”, “문제 없음”, “적정” → `양호`

## PDF 하이라이트

### `app/services/pdf_highlight_service.py`

PyMuPDF(`fitz`)로 PDF 텍스트 레이어를 읽고, 검증 결과와 RAG 결과가 가리키는 필드를 하이라이트한다.

핵심 역할:

- PDF 첫 페이지를 PNG로 렌더링
- 텍스트 블록/라인/단어 좌표 인덱싱
- 계약서 필드별 위치 탐색
- finding과 RAG 분석 항목을 highlight spec으로 변환
- 같은 field_path에 여러 spec이 있으면 더 위험한 review level을 우선
- PDF annotation 추가
- `highlighted.pdf`, `highlighted.png`, `highlighted_findings.json`, `extraction.json`, `rendered.png` 저장

좌표 체계:

- 내부 위치는 PDF page 좌표를 사용한다.
- 외부 JSON에는 `bbox_0_999`로 0~999 정규화 좌표를 저장한다.
- 프론트나 다른 뷰어가 페이지 크기와 무관하게 재사용할 수 있게 하기 위함이다.

색상:

- `주의`: 주황색 계열 `(1.0, 0.48, 0.22)`
- `보통`: 노란색 계열 `(1.0, 0.84, 0.25)`
- `양호`: 초록색 계열 `(0.42, 0.82, 0.42)`
- annotation opacity는 `0.2`

하이라이트 대상:

- 규칙 기반 finding
- 주소/상세주소/중개업 검증 성공 항목
- RAG 계약조건 분석
- 임차인에게 불리하다고 판단된 RAG 특약

특약 하이라이트 정책:

- 모든 특약을 무조건 칠하지 않는다.
- RAG 특약 분석에서 judgment에 “불리”가 포함된 특약만 하이라이트한다.
- 예: “보증금 반환 여부와 관계없이 즉시 인도” 또는 “모든 수리비 임차인 부담” 같은 특약.

## 분석 결과 기반 챗봇

### `app/services/contract_chat_service.py`

분석 완료 후 생성된 `combined_result.json`을 컨텍스트로 계약서 Q&A를 제공한다.

사용 방식:

```json
POST /api/contracts/chat
{
  "combined_result_url": "/outputs/20260429_100048_xxxxxxxx/combined_result.json",
  "question": "반려동물을 키우는데 도움이 되는 특약이 있을까?",
  "history": []
}
```

보안:

- `/outputs/.../combined_result.json`만 허용한다.
- `../` 등을 사용한 경로 탈출은 차단한다.
- `combined_result.json`이 아닌 파일은 챗봇 컨텍스트로 사용할 수 없다.

챗봇 컨텍스트:

- 계약 스냅샷
  - 임대차 유형
  - 목적물 주소
  - 임대할 부분
  - 보증금, 계약금, 잔금, 월세
  - 선불/후불, 매월 지급일
- 계약 조항
- 특약
- 규칙 기반 finding
- RAG 계약조건 분석
- RAG 특약 분석
- 전체 요약

질문 처리:

1. 질문에서 topic 추론
2. 질문 embedding 생성
3. 법령/가이드/특약 DB에서 관련 후보 검색
4. 질문이 특약 추천이면 유리한 특약 템플릿을 함께 제공
5. LLM이 JSON schema에 맞게 답변

추천 특약 템플릿:

- 반려동물 사육 허용 및 책임 범위
- 보증금 반환과 인도 동시이행
- 전입신고 및 확정일자 보장
- 노후 설비와 입주 전 하자 보수
- 관리비 항목과 정산 기준 명시
- 보증보험 가입 협조

반려동물 예시 문구:

```text
임대인은 임차인이 반려동물 1마리를 사육하는 것에 동의한다.
반려동물로 인해 발생한 직접적인 훼손은 임차인이 원상회복하되,
통상 사용에 따른 마모나 반려동물과 무관한 하자는 임차인의 책임으로 보지 않는다.
```

## 산출물 저장

### `app/services/verification_persistence.py`

검증 결과를 `backend/outputs/{YYYYMMDD_HHMMSS}_{uuid8}/` 아래 저장한다.

저장 파일:

- `extracted_contract.json`
  - LLM이 추출한 계약서 구조화 결과
- `verification_result.json`
  - 주소/중개사/임대료 검증 결과와 규칙 기반 분석
- `analysis_result.json`
  - 규칙 기반 finding만 별도 저장
- `combined_result.json`
  - 추출, 검증, RAG, 하이라이트 요약이 모두 합쳐진 최종 결과
- `rag_result.json`
  - RAG 검색 결과
- `rag_llm_payload.json`
  - RAG 분석 LLM 입력
- `rag_analysis_result.json`
  - RAG 분석 및 2차 법령 검증 결과
- `rendered.png`
  - 원본 첫 페이지 렌더링
- `highlighted.pdf`
  - annotation이 들어간 PDF
- `highlighted.png`
  - 하이라이트 PDF 첫 페이지 이미지
- `highlighted_findings.json`
  - 하이라이트 항목과 좌표
- `extraction.json`
  - PDF 텍스트 레이어에서 찾은 필드 좌표

### `app/presenters/verify_response.py`

내부 결과를 프론트가 쓰기 쉬운 응답으로 변환한다.

역할:

- 로컬 파일 경로를 `/outputs/...` 공개 URL로 변환
- 자동 검증 요약 생성
- RAG 요약 생성
- 프론트용 artifact URL 묶음 생성

`artifacts` 예:

```json
{
  "highlightedPdfUrl": "/outputs/.../highlighted.pdf",
  "highlightedImageUrl": "/outputs/.../highlighted.png",
  "combinedResultJsonUrl": "/outputs/.../combined_result.json",
  "ragAnalysisJsonUrl": "/outputs/.../rag_analysis_result.json"
}
```

## CLI

### `app/cli.py`

CLI에서 계약서 검증을 실행하고 전체 결과 JSON을 출력한다.

### `run_backend_check.py`

개발 중 빠르게 전체 파이프라인을 확인하기 위한 간단한 실행 스크립트다. 전체 결과 대신 주요 산출물 경로와 summary만 출력한다.

## 환경변수

`backend/.env`에서 읽는다.

필수:

- `OPENAI_API_KEY`
- `JUSO_ROAD_API_KEY`
- `JUSO_DETAIL_API_KEY`

DB:

- `DATABASE_URL`

또는:

- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

선택:

- `SAFELEASE_DEBUG_EXTRACTION=1`
  - LLM 추출 JSON 파싱 실패 시 원문/복구 JSON을 `outputs/debug`에 저장한다.

## 데이터 보강 도구

루트의 `rag_seed/`는 운영 API가 아니라 RAG DB 보강용 도구다.

- `rag_seed/build_seed.py`
  - 법제처 API로 주택임대차보호법, 민법, 공인중개사법 등 핵심 조문 추출
  - 임차인 보호 중심 위험 특약 60개 생성
- `rag_seed/load_seed.py`
  - 생성된 JSONL을 DB에 upsert
  - OpenAI embedding 생성 후 `source_chunk_embeddings`, `clause_library_embeddings`에 저장
- `rag_seed/dist/`
  - 생성 산출물 폴더이며 `.gitignore` 대상

현재 DB에는 법령 조문, 가이드, 위험 특약, 임대료 통계가 함께 들어간다.

## 현재 구조상 유지보수 메모

지금 구조는 MVP 백엔드로는 적절하다. 다만 아래 파일은 커졌기 때문에 기능이 더 늘면 분리를 권장한다.

### `rag_analysis_service.py`

현재 한 파일이 다음 역할을 모두 맡고 있다.

- RAG query 생성
- topic 추론
- embedding 검색
- rerank
- LLM 분석 prompt/schema
- 법령 근거 상세 연결
- 2차 법령 검증
- RAG 산출물 저장

추후 분리 후보:

- `rag_search.py`
- `rag_topics.py`
- `rag_prompting.py`
- `legal_basis_verifier.py`
- `rag_pipeline.py`

### `pdf_highlight_service.py`

현재 한 파일이 다음 역할을 모두 맡고 있다.

- PDF 텍스트 레이어 인덱싱
- 필드 위치 탐색
- 하이라이트 spec 생성
- annotation 렌더링
- artifact 저장

추후 분리 후보:

- `pdf_text_index.py`
- `highlight_locator.py`
- `highlight_specs.py`
- `highlight_renderer.py`

### 개인정보 주의

현재 구조는 분석 결과와 챗봇 컨텍스트에 계약서 원문, 주소, 이름, 전화번호, 주민등록번호 raw text가 포함될 수 있다. 실제 서비스화 단계에서는 다음을 추가하는 것이 좋다.

- OpenAI 요청 전 주민등록번호/전화번호 마스킹
- `combined_result.json` 보관 기간 정책
- `/outputs` 정적 공개 범위 제한
- 챗봇 컨텍스트 최소화 옵션

## 빠른 검증 명령

백엔드 문법 확인:

```powershell
python -c "from pathlib import Path; files=[str(p) for p in Path('backend/app').rglob('*.py')]; [compile(Path(f).read_text(encoding='utf-8'), f, 'exec') for f in files]; print(len(files), 'files ok')"
```

샘플 실행:

```powershell
cd backend
python run_backend_check.py sample.pdf
```

서버 실행:

```powershell
cd backend
uvicorn app.api:app --reload
```

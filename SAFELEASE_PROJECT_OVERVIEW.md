# SafeLease 프로젝트 전체 문서

이 문서는 SafeLease 프로젝트의 목적, 기능, 구조, 데이터 흐름, 실행 방법, 주요 파일, 산출물, 보안 고려사항을 한곳에 모은 프로젝트 설명서입니다. 취업용 포트폴리오 문서와 달리, 이 문서는 프로젝트를 유지보수하거나 다시 설명할 때 필요한 정보를 최대한 빠짐없이 담는 것을 목표로 합니다.

## 1. 프로젝트 요약

SafeLease는 주택 임대차 계약서 PDF를 업로드하면 계약서의 주요 내용을 구조화하고, 주소/중개업/임대료/특약/법령 근거를 종합 분석해 임차인 관점의 검토 결과를 제공하는 서비스입니다.

핵심 목표는 단순 계약서 요약이 아니라, 다음 질문에 답하는 것입니다.

- 계약서에 적힌 주소와 상세 호실이 실제로 확인되는가?
- 임대인/임차인 주소가 정상 주소로 조회되는가?
- 중개업 등록번호, 상호, 대표자, 소재지가 일치하는가?
- 보증금과 월세가 지역/면적 기준 참고 시세와 비교해 과도하지 않은가?
- 계약조건과 특약에 임차인에게 불리하거나 분쟁 소지가 있는 내용이 있는가?
- 분석 결과가 계약서 PDF의 어느 위치에 해당하는지 사용자가 직접 확인할 수 있는가?
- 사용자가 후속 질문을 하면 분석 결과와 법령/특약 근거를 바탕으로 답할 수 있는가?

## 1-1. 핵심 차별점과 증빙 수치

SafeLease는 일반적인 “PDF 업로드 + AI 요약” 프로젝트와 다르게, AI 결과를 검증 가능한 계약 검토 결과로 만들기 위한 장치를 여러 단계에 넣었습니다.

현재 워크스페이스에서 확인된 주요 수치:

- 백엔드/프론트/RAG seed 코드: 41개 파일
- 비공백 LOC: 약 7,346줄
- 백엔드 함수: 217개
- RAG 분석 서비스 함수: 54개
- PDF 하이라이트 서비스 함수: 47개
- 검증 파이프라인 단계: 18단계
- 백엔드 실행 산출물: 64회
- 통합 결과 `combined_result.json`이 생성된 실행: 60회
- RAG 분석 결과가 생성된 실행: 59회
- 법령 2차 검증 리뷰가 포함된 실행: 29회
- 대표 실행 artifact: 13개 파일
- 대표 실행 PDF 필드 좌표: 84개
- 대표 실행 하이라이트: 16개
- 대표 실행 RAG 분석 항목: 14개
- 대표 실행 법령 후보 검토: 27개
- 2차 법령 검증 결과: `direct` 3개, `supporting` 10개, `irrelevant` 14개
- 최종 법령 근거 상세: 13개
- 후보 대비 부적절/중복/미채택 근거 제거 비율: 51.9%
- 법령 2차 검증 포함 29회 실행 합산: 후보 리뷰 618개, 최종 근거 상세 247개, `irrelevant` 371개
- 29회 실행 합산 기준 후보 대비 제거/미채택 비율: 60.0%
- RAG topic 규칙: 21개
- query별 topic 규칙: 20개
- fallback topic map: 24개
- RAG seed: 핵심 법령 6개, 조문 참조 56개, 임차인 위험 특약 60개

채용 관점에서 가장 중요한 차별점:

- **검증 가능한 AI**: LLM 응답만 저장하지 않고 추출 JSON, 검증 JSON, RAG 검색 결과, LLM payload, 최종 분석, PDF 좌표, 하이라이트 PDF를 모두 저장합니다.
- **embedding-only가 아닌 RAG**: vector similarity 이후 topic, fallback, preferred legal refs, token overlap, primary authority, noise penalty를 반영해 rerank합니다.
- **근거 오염 제거**: 2차 LLM 검증으로 법령 후보를 `direct/supporting/irrelevant`로 분류하고 부적절 근거를 제거합니다.
- **원문 추적 가능성**: 분석 결과를 PDF field path와 연결해 사용자가 원문에서 확인할 수 있게 합니다.
- **도메인 데이터 구축**: 임차인 보호 관점의 위험 특약 60개와 핵심 법령 조문 seed를 직접 구성했습니다.
- **민감 문서 보안 고려**: 개인정보 마스킹과 챗봇 컨텍스트 경로 제한을 구현했습니다.
- **운영성/디버깅 고려**: LLM JSON 응답 복구, 디버그 원문 저장 옵션, 외부 사이트 자동화 retry/wait 로직을 구현했습니다.

면접용 압축 설명:

> SafeLease는 LLM 요약 앱이 아니라, 임대차 계약서 PDF에서 추출한 정보를 공공 API와 통계 DB로 검증하고, RAG 검색 결과를 hybrid reranking과 2차 법령 검증으로 정제한 뒤, 최종 판단을 원문 PDF 좌표와 연결한 계약 검토 시스템입니다.

## 2. 현재 프로젝트 구성

```text
safelease/
  backend/
    app/
      api.py
      cli.py
      core/
      presenters/
      services/
      validators/
    main.py
    requirements.txt
    run_backend_check.py
    outputs/
  frontend/
    src/
      app/
      components/
      context/
      lib/
      types/
    package.json
  rag_seed/
    build_seed.py
    load_seed.py
  sample.pdf
  SAFELEASE_PORTFOLIO_DRAFT.md
  SAFELEASE_PROJECT_OVERVIEW.md
```

코드 규모 기준 현재 확인된 값:

- 백엔드/프론트/RAG seed 코드: 41개 파일
- 비공백 LOC: 약 7,346줄
- 백엔드 실행 산출물: `backend/outputs` 아래 64회 실행 결과 확인
- 대표 실행 폴더 `backend/outputs/20260429_100048_5eb16df1` 기준 artifact 13개 생성

## 2-1. `outputs` 폴더로 본 개발 진화

`backend/outputs`에 남은 64회 실행 산출물을 기준으로 보면, 기능이 한 번에 완성된 것이 아니라 단계적으로 확장된 흔적이 있습니다.

단계별 흐름:

- **2026-04-21**: 4회 실행. `extraction.json`, `highlighted_findings.json`, `verification_result.json` 중심. PDF 필드 추출과 하이라이트 검증 단계.
- **2026-04-24**: 10회 실행. `combined_result.json`이 등장하고, 곧이어 `rag_analysis_result.json`도 생성되기 시작. 프론트/챗봇에서 재사용 가능한 통합 결과와 RAG 분석이 붙은 단계.
- **2026-04-28**: 18회 실행. RAG 분석과 하이라이트 산출물을 반복 생성하며 field locator와 artifact 구성을 다듬은 단계.
- **2026-04-29**: 10회 실행. `legal_basis_reviews`가 포함되기 시작. 법령 근거를 2차로 검증해 `direct/supporting/irrelevant`로 분류하는 단계.
- **2026-04-30 이후**: 22회 실행. RAG 분석, 2차 법령 검증, PDF 하이라이트, 통합 결과가 함께 생성되는 안정화 단계.

집계:

- 전체 실행: 64회
- `combined_result.json` 생성: 60회
- `rag_analysis_result.json` 생성: 59회
- 법령 2차 검증 리뷰 포함: 29회
- 2차 검증 포함 실행 합산 후보 리뷰: 618개
- 2차 검증 포함 실행 합산 최종 근거 상세: 247개
- 2차 검증 포함 실행 합산 `irrelevant`: 371개

이 흐름은 포트폴리오에서 “단순 구현”보다 “반복 실행을 통해 RAG 근거 품질과 산출물 구조를 개선했다”는 증거로 사용할 수 있습니다.

## 3. 기술 스택

백엔드:

- Python
- FastAPI
- OpenAI API
- PostgreSQL
- pgvector
- psycopg
- Selenium
- PyMuPDF
- python-dotenv
- requests

프론트엔드:

- Next.js
- React
- TypeScript
- Tailwind CSS

외부 데이터/서비스:

- OpenAI file/response/embedding API
- 도로명주소 API
- VWorld 부동산중개업 조회
- 법제처 Open API
- 자체 PostgreSQL 임대료 통계/RAG DB

## 4. 전체 처리 흐름

```text
사용자 PDF 업로드
-> FastAPI /api/contracts/verify
-> 업로드 파일 검증
-> 임시 PDF 저장
-> OpenAI 파일 업로드
-> LLM으로 계약서 구조화 JSON 추출
-> 추출 결과 정규화
-> 목적물 주소 및 상세주소 검증
-> 임대인/임차인 주소 검증
-> 중개업 등록번호 조회
-> 임대료 참고 시세 비교
-> 규칙 기반 finding 생성
-> RAG 검색 및 계약조건/특약 분석
-> LLM 2차 법령 근거 검증
-> PDF 필드 좌표 추출
-> 개인정보 마스킹
-> 하이라이트 PDF/PNG 생성
-> JSON 산출물 저장
-> 프론트 결과 화면 표시
-> 분석 결과 기반 챗봇 질의응답
```

## 5. 백엔드 API

### `GET /health`

서버 상태 확인용 API입니다.

응답:

```json
{
  "status": "ok"
}
```

구현 위치:

- `backend/app/api.py`

### `POST /api/contracts/verify`

계약서 PDF를 업로드해 전체 검증 파이프라인을 실행합니다.

입력:

- multipart form-data
- field: `file`
- PDF 확장자만 허용
- 빈 파일이면 400 오류 반환

주요 응답:

- `result`: 마스킹된 전체 분석 결과
- `review`: 프론트 요약용 검토 문구
- `ragAnalysis`: RAG 상세 분석 결과
- `ragReview`: RAG 요약 카드용 데이터
- `artifacts`: 하이라이트 PDF, PNG, JSON 산출물 URL
- `highlightSummary`: 하이라이트 요약 및 항목

구현 위치:

- API: `backend/app/api.py`
- 응답 변환: `backend/app/presenters/verify_response.py`
- 서비스 진입: `backend/app/services/contract_service.py`

### `POST /api/contracts/chat`

분석 완료 후 저장된 `combined_result.json`을 기반으로 계약서 Q&A를 제공합니다.

입력:

```json
{
  "combined_result_url": "/outputs/20260429_100048_5eb16df1/combined_result.json",
  "question": "반려동물을 키우는데 도움이 되는 특약이 있을까?",
  "history": []
}
```

보안 정책:

- `/outputs/...` 경로만 허용
- `combined_result.json` 파일만 허용
- resolved path가 `backend/outputs` 하위인지 검사
- 경로 탈출 차단

구현 위치:

- API: `backend/app/api.py`
- 챗봇 서비스: `backend/app/services/contract_chat_service.py`

## 6. 백엔드 모듈별 역할

### `backend/app/api.py`

FastAPI 서버 진입점입니다.

역할:

- CORS 설정
- `/outputs` 정적 파일 mount
- `/health`
- `/api/contracts/verify`
- `/api/contracts/chat`
- 업로드 파일 검증
- 예외를 HTTP 응답으로 변환

### `backend/app/core/common.py`

공통 상수와 유틸리티를 관리합니다.

주요 항목:

- `PROJECT_ROOT`
- `OUTPUT_DIR`
- `SAMPLE_PDF_PATH`
- `ENV_PATH`
- `.env` 로드
- 필수 환경변수 조회
- JSON/텍스트 저장
- 검증 결과 공통 포맷 생성

공통 검증 결과 포맷:

```json
{
  "status": "success | not_found | partial_match | query_failed",
  "data": {},
  "error_code": null,
  "error_message": null,
  "debug": {}
}
```

### `backend/app/core/progress.py`

CLI/서버 로그용 진행 단계 출력 모듈입니다.

특징:

- 전체 18단계 기준
- 단계별 elapsed time과 total elapsed time 출력
- 예: `[09/18] 10:00:00 (+120ms, total 3000ms) 목적물 주소 및 상세주소 검증 중`

### `backend/app/services/contract_service.py`

파일 경로 또는 업로드 스트림을 검증 파이프라인에 연결하는 얇은 서비스 계층입니다.

역할:

- 로컬 PDF 검증
- 업로드 스트림을 임시 PDF로 저장
- 검증 후 임시 파일 삭제
- 검증 결과 산출물 저장 호출

### `backend/app/services/contract_extractor.py`

OpenAI를 사용해 PDF 계약서를 구조화 JSON으로 추출합니다.

주요 역할:

- PDF를 OpenAI file storage에 업로드
- 계약서 추출 프롬프트 생성
- `gpt-5.4-mini`로 구조화 JSON 추출
- JSON 파싱 실패 시 응답 보정

파싱 안정성 보강:

- LLM 응답에 ```json 코드블록이 섞여도 제거
- 응답 앞뒤에 설명이 붙어도 첫 JSON 객체만 추출
- 문자열 내부의 잘못된 escape를 보정
- `SAFELEASE_DEBUG_EXTRACTION=1`이면 원문 응답과 복구 JSON을 `outputs/debug`에 저장

이 기능은 LLM 출력이 항상 순수 JSON으로 오지 않는 현실적인 문제를 줄이기 위한 안정화 장치입니다.

중요 추출 정책:

- 전세/월세는 문서 상단 체크박스 기준으로 판단
- 금액은 `raw_text`, `korean_text`, `numeric_text`, `normalized_value`를 함께 추출
- 날짜는 원문과 정규화 값을 모두 유지
- 제1조의 보증금/차임 정보는 `payment`에 집중 관리
- 특약 본문과 계좌번호성 텍스트는 분리

### `backend/app/services/contract_normalizer.py`

LLM 추출 결과를 검증 API에 쓰기 쉬운 형태로 정리합니다.

정규화 대상:

- 목적물 주소
- 임대할 부분
- 면적
- 보증금
- 월세
- 임대인/임차인 이름과 주소
- 중개업 등록번호
- 중개업 소재지, 상호, 대표자
- VWorld 조회용 시도/시군구

### `backend/app/services/contract_verifier.py`

계약서 검증의 오케스트레이터입니다.

주요 순서:

1. PDF 업로드
2. 계약서 구조화 JSON 추출
3. 검증 입력 정규화
4. 목적물 주소 및 상세주소 검증
5. 임대인/임차인 주소 검증
6. 중개업 등록번호 조회
7. 임대료 참고 시세 비교
8. 규칙 기반 finding 생성

핵심 함수:

- `verify_contract_pdf`
- `build_verification_summary`
- `build_missing_address_result`
- `build_missing_broker_result`

### `backend/app/services/verification_analysis.py`

주소/중개사/임대료 검증 결과를 사람이 읽을 수 있는 finding으로 변환합니다.

review level:

- `error` -> `주의`
- `warning` -> `보통`
- `info` -> `양호`

전체 판정:

- error가 있으면 `overall_status = fail`, `review_level = 주의`
- warning만 있으면 `overall_status = warning`, `review_level = 보통`
- finding이 없으면 `overall_status = pass`, `review_level = 양호`

대표 finding:

- 목적물 주소 누락
- 기본주소 조회 실패
- 상세주소 불일치
- 임대인/임차인 주소 조회 실패
- 중개업 등록번호 누락
- 중개업 등록번호/대표자/상호/소재지 불일치
- 환산월세 참고 범위 초과

### `backend/app/validators/address_validator.py`

도로명주소 API로 주소와 상세주소를 검증합니다.

필수 환경변수:

- `JUSO_ROAD_API_KEY`
- `JUSO_DETAIL_API_KEY`

처리 방식:

1. 기본주소로 도로명주소 검색
2. `leased_part`에서 동/층/호 추출
3. 상세주소 API로 호실 목록 조회
4. 계약서의 동/층/호와 API 목록 비교

상태 분리:

- 기본주소 검색 실패: `not_found`
- 기본주소는 확인됐지만 상세주소 목록 확인 불가: `partial_match`
- 상세주소 목록은 있지만 동/층/호 불일치: `not_found` + `DETAIL_VALUE_NOT_FOUND`
- HTTP 실패: `query_failed` + `ROAD_HTTP_FAILED` 또는 `DETAIL_HTTP_FAILED`
- JSON 파싱 실패: `query_failed` + `ROAD_JSON_PARSE_FAILED` 또는 `DETAIL_JSON_PARSE_FAILED`

이렇게 상태를 나눈 이유는 “주소 자체가 틀린 것”과 “주소는 맞지만 호실 확인이 안 되는 것”의 위험도가 다르기 때문입니다.

상세주소 예:

- `104동 1702호 전부` -> `dong=104동`, `ho=1702호`
- `5층 503호 전부` -> `floor=5층`, `ho=503호`

### `backend/app/validators/broker_validator.py`

VWorld 부동산중개업 조회 페이지를 Selenium으로 자동 조회합니다.

조회 입력:

- 시도
- 시군구
- 중개업 등록번호

검증 대상:

- 등록번호
- 상호
- 사무소 소재지
- 대표자명
- 등록일
- 상태
- 업무 시작/종료일

특징:

- Chrome headless 모드
- 최대 3회 재시도
- select box 로딩 대기
- 검색 결과 테이블 파싱

자동화 안정화:

- 시군구 option이 로딩될 때까지 polling
- 등록번호 input이 안정적으로 잡힐 때까지 wait
- loading overlay가 사라질 때까지 wait
- 결과 table 렌더링 대기
- `NoSuchElementException`, `StaleElementReferenceException`, `TimeoutException`을 retryable error로 분리
- retryable DOM error는 최대 3회 재시도

VWorld 조회는 정식 JSON API가 아니라 웹 페이지 DOM을 다뤄야 하므로, 단순 Selenium 클릭보다 로딩/DOM 변동을 견디는 구조가 중요했습니다.

### `backend/app/services/rent_reference_service.py`

보증금과 월세를 환산월세로 변환한 뒤 DB의 참고 통계와 비교합니다.

기본 전월세전환율:

```python
DEFAULT_CONVERSION_RATE = 0.045
```

환산월세 공식:

```text
환산월세(만원) = 월세금(만원) + 보증금(만원) * 0.045 / 12
```

통계 선택 우선순위:

1. 법정동 + 면적구간: `dong_area`
2. 시군구 + 면적구간: `area`
3. 법정동 전체: `dong`
4. 시군구 전체: `region`

표본 기준:

- `dong_area`는 표본 수 10건 이상일 때 직접 사용
- 표본 수 30건 이상이면 `confidence = strong`
- 30건 미만이면 `confidence = weak`

비교 기준:

- P90 초과: `high`
- P75 초과: `slightly_high`
- P25 미만: `low`
- P25~P75: `normal`

### `backend/app/services/rag_analysis_service.py`

계약조건과 특약을 법령/가이드/유사 특약 라이브러리와 비교해 LLM 분석 결과를 생성합니다.

기본 모델:

```python
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_ANALYSIS_MODEL = "gpt-5.4-mini"
```

검색 설정:

```python
LEGAL_FETCH_K = 12
GUIDE_FETCH_K = 12
CLAUSE_FETCH_K = 8
LEGAL_MIN_SIMILARITY = 0.4
GUIDE_MIN_SIMILARITY = 0.4
CLAUSE_MIN_SIMILARITY = 0.4
```

분석 대상:

- 보증금 조건
- 잔금 조건
- 월 차임 조건
- 차임 지급 방식
- 임대차 기간 조건
- 목적물 표시
- 전세/월세 유형 확인
- 보증금 합계 확인
- 잔금 구조 확인
- 임대차 기간 확인
- 중도금 기재 확인
- 특약별 분석

RAG 검색 흐름:

1. 분석 item별 query 생성
2. query embedding 생성
3. 법령/가이드 chunk 검색
4. 특약 라이브러리 검색
5. topic 일치, 일반 가이드, 선호 조문, 토큰 겹침 기준 rerank
6. LLM 분석 payload 생성
7. LLM이 계약조건/특약 분석
8. LLM 2차 법령 근거 검증
9. `irrelevant` 근거 제거
10. RAG 산출물 저장

RAG 품질 개선 전략:

SafeLease의 RAG는 embedding similarity만으로 문서를 고르는 구조가 아닙니다. 1차 후보 검색에는 vector similarity를 쓰지만, 최종 LLM 입력에 들어갈 근거는 여러 규칙을 결합해 다시 정렬하고 압축합니다.

1. Query item 분해

계약서 전체를 하나의 query로 검색하지 않습니다. 보증금, 잔금, 월 차임, 차임 지급 방식, 임대차 기간, 목적물 표시, 특약별 내용처럼 분석 단위를 나눕니다. 이렇게 해야 “보증금 반환” 근거와 “차임 지급 시기” 근거가 서로 섞이는 문제를 줄일 수 있습니다.

2. 진단성 query 생성

계약서에 직접 문장으로 적힌 내용만 검색하지 않고, 추출된 값에서 파생되는 이상 징후도 query로 만듭니다.

- 전세/월세 체크가 불명확한 경우
- 계약금 + 중도금 + 잔금 합계가 보증금과 맞지 않는 경우
- 잔금이 보증금보다 큰 경우
- 임대차 종료일이 인도일보다 빠른 경우
- 중도금 원문 흔적은 있는데 금액 정규화가 실패한 경우

3. Topic inference

`infer_topic`, `infer_topic_from_query`에서 query 문구와 label을 기반으로 topic을 추론합니다.

예시 topic:

- `deposit_return`
- `priority_protection`
- `rent_increase`
- `broker_duty`
- `management_fee`
- `repair_and_defect`
- `registry_and_rights`
- `identity_and_authority`
- `payment_schedule`
- `payment_structure`
- `pet`

4. Topic fallback 검색

topic이 너무 좁으면 필요한 근거를 놓칠 수 있으므로 `build_search_topics`에서 fallback topic을 함께 검색합니다.

예:

- `deposit_return` -> `deposit_protection`, `contract_basics`, `general_guidance`
- `priority_protection` -> `deposit_protection`, `registry_and_rights`, `general_guidance`
- `repair_and_defect` -> `repair_and_defect`, `special_clause`, `general_guidance`
- `pet` -> `special_clause`, `general_guidance`

5. Preferred legal refs 부스팅

계약조건별로 우선 검토할 법령 조문을 `build_preferred_legal_refs`에서 지정합니다. 검색 결과에 해당 조문이 있으면 rerank 점수를 높입니다.

예:

- 차임/월세/지급 방식: 민법 제633조, 주택임대차보호법 제7조, 제10조
- 보증금/잔금/계약금/중도금: 주택임대차보호법 제10조, 민법 제565조, 주택임대차보호법 제13조
- 기간/인도일/종료일: 민법 제623조, 주택임대차보호법 제4조
- 중개/설명서: 공인중개사법 제25조, 공인중개사법 시행규칙 제16조
- 전입/확정일자/선순위/보증금 반환: 주택임대차보호법 제3조, 제10조, 제13조

6. Hybrid reranking

`score_match`는 vector similarity에 다음 요소를 더해 점수를 계산합니다.

- topic 일치 bonus
- `general_guidance` 보조 bonus
- primary authority bonus
- law source bonus
- query와 후보 조문 간 token overlap bonus
- preferred legal refs bonus
- 너무 짧은 텍스트 penalty
- 제목성/맥락 약한 조문 penalty

특약 검색도 `rerank_clause_matches`에서 similarity, token overlap, topic 일치, special clause fallback, favorability를 함께 봅니다.

7. LLM 입력 근거 압축

검색 후보를 많이 가져오더라도 LLM 입력에는 압축된 근거만 전달합니다.

- 법령 근거: 상위 3개 수준
- 가이드 근거: 상위 3개 수준
- 유사 특약: 상위 2개 수준

이렇게 prompt noise를 줄이고, LLM이 관련 없는 근거를 끌어와 판단하는 가능성을 낮춥니다.

8. 2차 법령 근거 검증

1차 분석이 끝난 뒤, 분석 문장과 후보 조문 전문을 다시 LLM에 넣어 법령 근거 적합성을 검증합니다.

분류:

- `direct`: 판단을 직접 뒷받침
- `supporting`: 배경 또는 간접 참고
- `irrelevant`: 해당 분석 근거로 부적절

최종 결과에서는 `irrelevant`를 제거하고, 남은 근거에는 조문 내용과 relevance/confidence/why_relevant를 함께 붙입니다.

대표 실행 수치:

- 실행 폴더: `backend/outputs/20260429_100048_5eb16df1`
- 계약조건/특약 분석 항목: 14개
- 법령 근거 후보 검토: 27개
- `direct`: 3개
- `supporting`: 10개
- `irrelevant`: 14개
- 최종 근거 상세 유지: 13개
- 후보 대비 최종 채택: 48.1%
- 후보 대비 부적절/중복/미채택 근거 제거: 51.9%
- 분석 레벨: 양호 7개, 주의 7개

관련 함수:

- `build_query_items`
- `build_diagnostics`
- `infer_topic`
- `infer_topic_from_query`
- `build_search_topics`
- `build_preferred_legal_refs`
- `score_match`
- `rerank_chunk_matches`
- `rerank_clause_matches`
- `build_legal_basis_verification_payload`
- `apply_legal_basis_verification`

2차 법령 근거 검증:

- 후보 조문을 `direct`, `supporting`, `irrelevant`로 분류
- `direct`: 판단을 직접 뒷받침
- `supporting`: 배경/간접 참고
- `irrelevant`: 해당 분석 근거로 부적절

### `backend/app/services/rag_contract_rules.py`

RAG 분석 결과와 PDF 하이라이트 대상 필드를 연결하는 규칙을 관리합니다.

예:

- `보증금 조건` -> `payment.deposit`
- `잔금 조건` -> `payment.balance`
- `월 차임 조건` -> `payment.monthly_rent`
- `차임 지급 방식` -> `payment.monthly_due_day`
- `임대차 기간 조건` -> `contract_terms[article_no=제2조].content`
- 특약 -> `special_terms[index].content`

또한 LLM judgment 문구를 기반으로 review level을 보정합니다.

### `backend/app/services/pdf_highlight_service.py`

PDF 원문과 분석 결과를 연결해 시각적 산출물을 생성합니다.

주요 기능:

- PDF 첫 페이지 PNG 렌더링
- 텍스트 레이어를 word/line/block 단위로 인덱싱
- 계약서 필드 위치 탐색
- 좌표를 `bbox_0_999`로 정규화
- 규칙 기반 finding과 RAG 분석을 하이라이트 spec으로 변환
- review level별 색상 annotation 추가
- 개인정보 마스킹
- `highlighted.pdf`, `highlighted.png`, `extraction.json`, `highlighted_findings.json` 저장

하이라이트 색상:

- `주의`: 주황
- `보통`: 노랑
- `양호`: 초록

개인정보 마스킹:

- 이름
- 주민등록번호
- 전화번호
- 중개사 대표자명
- 계약금 영수자명

### `backend/app/services/privacy_masking.py`

외부 공개용 결과에서 민감정보를 마스킹합니다.

마스킹 규칙:

- 이름: `홍길동` -> `홍*동`
- 2글자 이름: `길동` -> `길*`
- 주민등록번호: 뒤 6자리 마스킹
- 전화번호: 끝 4자리 마스킹

적용 대상:

- JSON 결과
- PDF 하이라이트 산출물
- 공개 응답 payload

### `backend/app/services/verification_persistence.py`

검증 실행 결과를 `backend/outputs/{YYYYMMDD_HHMMSS}_{uuid8}` 아래 저장합니다.

저장 흐름:

1. 실행 폴더 생성
2. 추출/검증/규칙 분석 JSON 저장
3. RAG 분석 실행 및 저장
4. PDF 하이라이트 산출물 생성
5. 마스킹된 `combined_result.json` 저장

### `backend/app/presenters/verify_response.py`

내부 검증 결과를 프론트엔드가 바로 사용하기 좋은 응답으로 변환합니다.

역할:

- 로컬 파일 경로를 `/outputs/...` 공개 URL로 변환
- 자동 검증 요약 생성
- RAG 요약 생성
- artifact URL 생성
- passed check 목록 생성

### `backend/app/services/contract_chat_service.py`

분석 결과 기반 계약서 Q&A와 특약 추천을 제공합니다.

주요 기능:

- `combined_result.json` 로드
- 계약 스냅샷 구성
- 질문 topic 추론
- 법령/특약 DB 추가 검색
- OpenAI JSON schema 응답 생성
- 임차인에게 유리한 특약 템플릿 fallback

추천 특약 템플릿:

- 반려동물 사육 허용 및 책임 범위
- 보증금 반환과 인도 동시이행
- 전입신고 및 확정일자 보장
- 노후 설비와 입주 전 하자 보수
- 관리비 항목과 정산 기준 명시
- 보증보험 가입 협조

## 7. 프론트엔드 구조

프론트엔드는 Next.js 기반으로 PDF 업로드, 분석 진행, 결과 확인, 챗봇 질의응답 화면을 제공합니다.

### 주요 페이지

`frontend/src/app/page.tsx`

- 업로드 첫 화면
- PDF 파일 선택
- 분석 시작

`frontend/src/app/analyzing/page.tsx`

- 분석 진행 중 화면
- 백엔드 단일 요청 완료를 기다리는 구조

`frontend/src/app/result/page.tsx`

- 분석 결과 화면
- 결과가 없으면 업로드 화면으로 이동 안내
- `ResultTabs`에 결과 표시 책임 위임

### 상태 관리

`frontend/src/context/ContractFlowProvider.tsx`

역할:

- 선택 파일 상태
- 분석 요청 상태
- 분석 결과 상태
- preview mode
- 챗봇 입력/응답 상태
- sessionStorage 저장/복원
- 업로드 -> 분석 중 -> 결과 화면 라우팅

sessionStorage key:

- `safelease.fileName`
- `safelease.result`

### API 클라이언트

`frontend/src/lib/api.ts`

역할:

- `NEXT_PUBLIC_API_BASE_URL` 또는 기본 `http://127.0.0.1:8000` 사용
- 계약서 검증 요청
- 챗봇 질문 요청
- artifact URL resolve

### 타입 정의

`frontend/src/types/contract.ts`

주요 타입:

- `ReviewLevel`
- `Finding`
- `RagCondition`
- `RagSpecialTerm`
- `RentReferenceVerification`
- `VerifyResponse`
- `ContractChatResponse`
- `ChatMessage`

### 주요 컴포넌트

`UploadCard.tsx`

- PDF 업로드 카드
- 제출 버튼
- 오류 메시지 표시

`PreviewPanel.tsx`

- 원본/하이라이트 이미지 또는 PDF 미리보기

`ReviewPanel.tsx`

- 자동 검증 결과
- 임대료 참고 시세
- RAG 요약
- 챗봇
- 계약조건 분석
- 특약 분석

`ResultTabs.tsx`

- 결과 화면 탭 구성

`RentReferenceBar.tsx`

- 환산월세와 참고 시세 비교 시각화

`LegalBasisDetails.tsx`

- 법령 근거 상세 표시

`ChatBlock.tsx`

- 계약서 Q&A 입력 및 응답 표시

## 8. RAG 데이터 구축 도구

`rag_seed`는 운영 API가 아니라 RAG DB를 구축하기 위한 보조 도구입니다.

### `rag_seed/build_seed.py`

역할:

- 법제처 Open API에서 핵심 법령 조문 수집
- 임차인 보호 관점의 위험 특약 seed 생성
- JSONL 파일로 저장

핵심 법령:

- 주택임대차보호법
- 주택임대차보호법 시행령
- 민법
- 공인중개사법
- 공인중개사법 시행규칙
- 부동산 거래신고 등에 관한 법률

생성 파일:

- `source_documents.jsonl`
- `source_chunks.jsonl`
- `tenant_risk_clauses.jsonl`
- `manifest.json`

위험 특약 seed:

- 보증금 반환 전 명도 요구
- 전입신고 제한
- 확정일자 제한
- 선순위 담보 설정 허용
- 모든 수리비 임차인 부담
- 과도한 원상복구
- 관리비 세부내역 미기재
- 중도해지 위약금 과다
- 갱신요구권 포기
- 반려동물 위약금 과다
- 임대인 자유 출입
- 보증보험 가입 제한 등

### `rag_seed/load_seed.py`

역할:

- JSONL seed를 PostgreSQL에 upsert
- OpenAI embedding 생성
- `source_chunk_embeddings`, `clause_library_embeddings`에 vector 저장

관련 DB 테이블:

- `source_documents`
- `source_chunks`
- `source_chunk_embeddings`
- `clause_library`
- `clause_library_embeddings`

## 9. 데이터베이스 사용 영역

SafeLease는 PostgreSQL을 다음 용도로 사용합니다.

임대료 참고 시세:

- `rent_reference_stats`

RAG 법령/가이드:

- `source_documents`
- `source_chunks`
- `source_chunk_embeddings`

RAG 특약 라이브러리:

- `clause_library`
- `clause_library_embeddings`

임대료 통계 주요 컬럼:

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

## 10. 산출물 구조

각 검증 실행은 다음 폴더에 저장됩니다.

```text
backend/outputs/{YYYYMMDD_HHMMSS}_{uuid8}/
```

대표 산출물:

- `extracted_contract.json`: LLM 추출 계약서 구조화 결과
- `verification_result.json`: 주소/중개업/임대료 검증 결과
- `analysis_result.json`: 규칙 기반 finding
- `combined_result.json`: 프론트/챗봇용 통합 결과
- `rag_result.json`: RAG 검색 결과
- `rag_llm_payload.json`: LLM 분석 입력
- `rag_analysis_result.json`: RAG 최종 분석 및 2차 법령 검증 결과
- `rendered.png`: 원본 PDF 첫 페이지 렌더링
- `highlighted.pdf`: 하이라이트 annotation이 들어간 PDF
- `highlighted.png`: 하이라이트 PDF 첫 페이지 이미지
- `highlighted_findings.json`: 하이라이트 항목과 좌표
- `extraction.json`: PDF 텍스트 레이어 필드 좌표
- `result.json`: 하이라이트 생성 결과 요약

대표 실행 결과:

- 실행 폴더: `backend/outputs/20260429_100048_5eb16df1`
- PDF 필드 좌표: 84개
- 하이라이트: 16개
- 하이라이트 레벨: 주의 8개, 양호 8개
- RAG 분석 항목: 14개
- 법령 후보 검토: 27개
- 최종 법령 근거 상세: 13개

## 11. 환경변수

백엔드는 `backend/.env`를 로드합니다.

필수:

```text
OPENAI_API_KEY=
JUSO_ROAD_API_KEY=
JUSO_DETAIL_API_KEY=
```

DB:

```text
DATABASE_URL=
```

또는:

```text
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_DB=rent
POSTGRES_USER=rent
POSTGRES_PASSWORD=rent1234
```

선택:

```text
SAFELEASE_DEBUG_EXTRACTION=1
LAW_API_OC=
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## 12. 실행 방법

### 백엔드 의존성 설치

```powershell
cd backend
python -m pip install -r requirements.txt
```

### 백엔드 서버 실행

```powershell
cd backend
uvicorn app.api:app --reload
```

기본 주소:

```text
http://127.0.0.1:8000
```

### 백엔드 smoke check

```powershell
cd backend
python run_backend_check.py sample.pdf
```

루트의 `sample.pdf`를 사용할 경우:

```powershell
python backend/run_backend_check.py sample.pdf
```

### 프론트엔드 실행

```powershell
cd frontend
npm install
npm run dev
```

기본 주소:

```text
http://localhost:3000
```

### 프론트엔드 빌드

```powershell
cd frontend
npm run build
```

### 프론트엔드 lint

```powershell
cd frontend
npm run lint
```

## 13. 대표 사용자 시나리오

1. 사용자가 PDF 계약서를 업로드합니다.
2. 프론트가 `/api/contracts/verify`로 파일을 전송합니다.
3. 백엔드가 PDF를 LLM에 전달해 구조화 JSON을 얻습니다.
4. 주소, 상세주소, 중개업 정보, 임대료를 검증합니다.
5. 규칙 기반 finding을 생성합니다.
6. RAG가 계약조건과 특약을 법령/가이드/특약 라이브러리와 비교합니다.
7. LLM이 분석 결과를 생성합니다.
8. LLM 2차 검증이 법령 근거의 적합성을 분류합니다.
9. PDF 원문 필드 위치를 찾아 하이라이트합니다.
10. 개인정보를 마스킹한 산출물을 저장합니다.
11. 프론트가 요약, 하이라이트, 임대료 비교, 법령 근거, 특약 분석을 보여줍니다.
12. 사용자가 챗봇에 질문하면 `combined_result.json`과 RAG 검색 근거를 바탕으로 답변합니다.

## 14. 주요 설계 의도

### 검증 가능한 AI 결과

LLM 답변만 보여주지 않고 다음 산출물을 함께 저장합니다.

- 추출 JSON
- 검증 JSON
- RAG 검색 결과
- LLM payload
- 최종 분석 결과
- PDF 좌표 JSON
- 하이라이트 PDF

이 구조 덕분에 분석 결과가 어떤 입력과 어떤 근거에서 나왔는지 추적할 수 있습니다.

### 공공 API + RAG + 규칙 기반 분석 결합

SafeLease는 LLM 하나에 모든 판단을 맡기지 않습니다.

- 주소: 도로명주소 API
- 중개업: VWorld 조회
- 임대료: 통계 DB
- 계약조건/특약: 법령 RAG + LLM
- 최종 요약: 규칙 기반 finding + LLM 분석

### 법령 근거 오염 방지

RAG는 유사도가 높아도 실제 판단 근거로 부적절한 조문이 섞일 수 있습니다. 이를 줄이기 위해 embedding 검색만 사용하지 않고 topic fallback, preferred legal refs, hybrid reranking, LLM 입력 근거 압축, 2차 LLM 검증을 함께 적용했습니다.

분류:

- `direct`
- `supporting`
- `irrelevant`

최종 결과에서는 `irrelevant` 근거를 제거합니다.

이 설계의 핵심은 “가까운 문서”를 찾는 것이 아니라 “계약 판단 근거로 쓸 수 있는 문서”를 남기는 것입니다.

### PDF 원문과 분석 결과 연결

사용자가 분석 결과만 읽는 것이 아니라, 원문 PDF의 어느 위치가 문제인지 확인할 수 있게 했습니다.

핵심 구현:

- PDF 텍스트 레이어 인덱싱
- 필드 path와 원문 좌표 연결
- RAG finding과 field path 매핑
- annotation 기반 PDF 하이라이트

### 개인정보 보호

계약서는 민감정보가 포함된 문서입니다. 현재 구현은 결과 저장과 공개 응답 단계에서 이름, 주민등록번호, 전화번호를 마스킹합니다.

## 14-1. 성능 개선/품질 개선 관점 정리

이 프로젝트에서 “좋아졌다”고 말할 수 있는 부분은 단순 처리 속도보다 RAG 품질, 결과 신뢰도, 검증 가능성, 보안 경계입니다.

### RAG 근거 품질 개선

문제:

- embedding similarity만으로는 단어가 비슷한 조문이 근거로 붙을 수 있습니다.
- 예를 들어 차임, 보증금, 해지처럼 법령 전반에 자주 등장하는 단어는 실제 판단 근거와 무관한 조문도 검색될 수 있습니다.

개선:

- query item을 계약조건/특약별로 분해
- topic inference로 검색 의도를 좁힘
- fallback topic으로 누락 방지
- preferred legal refs로 도메인상 중요한 조문을 부스팅
- token overlap과 primary authority 여부를 rerank에 반영
- 너무 짧거나 제목성에 가까운 조문은 penalty
- 2차 LLM 검증으로 `irrelevant` 제거

대표 수치:

- 후보 법령 27개 검토
- `irrelevant` 14개 제거
- 최종 근거 상세 13개 유지
- 후보 대비 51.9%를 부적절/중복/미채택 근거로 제거
- 법령 2차 검증 포함 29회 실행 합산 기준 후보 리뷰 618개 중 최종 근거 상세 247개 유지
- 29회 합산 기준 `irrelevant` 371개, 후보 대비 제거/미채택 비율 60.0%

### 결과 검증 가능성 개선

문제:

- AI 분석 결과만 있으면 사용자가 “왜 그렇게 판단했는지” 확인하기 어렵습니다.

개선:

- 추출 JSON, 검증 JSON, RAG 검색 결과, LLM payload, 최종 분석 결과를 모두 저장
- PDF 텍스트 레이어에서 field path별 좌표를 추출
- 하이라이트 PDF/PNG 생성

대표 수치:

- 대표 실행 artifact 13개
- PDF field 84개 위치 추출
- 하이라이트 16개 생성

### 도메인 적합성 개선

문제:

- 일반 법령 검색만으로는 임차인에게 불리한 특약을 잘 잡기 어렵습니다.

개선:

- 임차인 보호 관점의 위험 특약 60개 seed 구축
- 핵심 법령 6개와 조문 참조 56개를 RAG DB에 적재
- 특약 검색 시 risk level, favorability, legality status를 함께 활용

### 외부 연동 안정성 개선

문제:

- LLM 응답은 항상 완벽한 JSON이 아닐 수 있습니다.
- VWorld 중개업 조회는 DOM 로딩과 select option 지연이 있어 Selenium 자동화가 불안정할 수 있습니다.
- 주소 검증은 기본주소와 상세주소 실패 원인이 다릅니다.

개선:

- LLM 응답에서 첫 JSON 객체를 추출하고, 코드블록과 잘못된 escape를 보정
- `SAFELEASE_DEBUG_EXTRACTION=1`로 원문 응답/복구 JSON 저장
- VWorld DOM 로딩 wait, loading overlay wait, retryable DOM error 3회 재시도
- 주소 검증 결과를 `not_found`, `partial_match`, `query_failed`로 세분화

포트폴리오 포인트:

- “AI/외부 API는 실패한다”는 전제에서 실패 상태와 복구 경로를 설계했습니다.

### 보안/개인정보 품질 개선

문제:

- 계약서는 이름, 주민등록번호, 전화번호, 주소가 포함된 민감 문서입니다.
- 챗봇이 파일 경로를 직접 받으면 임의 파일 접근 위험이 생길 수 있습니다.

개선:

- JSON/PDF 공개 산출물에서 이름, 주민등록번호, 전화번호 마스킹
- 챗봇 컨텍스트는 `/outputs/.../combined_result.json`만 허용
- resolved path가 `OUTPUT_DIR` 하위인지 검사해 path traversal 차단

## 15. 현재 한계와 개선 필요 영역

### 테스트

현재는 `run_backend_check.py`와 실행 산출물 중심으로 검증되어 있습니다. 취업 포트폴리오나 실제 서비스화를 위해서는 다음 테스트가 있으면 좋습니다.

- 주소 validator 단위 테스트
- 임대료 환산월세 계산 테스트
- RAG topic inference 테스트
- 법령 근거 2차 검증 mock 테스트
- PDF 필드 locator 테스트
- API 통합 테스트
- 프론트 컴포넌트 테스트

### RAG 평가

현재 RAG 개선은 코드 구조와 산출물로 증빙할 수 있지만, 정량 평가셋은 별도로 없습니다.

추가하면 좋은 것:

- 계약조건별 기대 법령 근거 정답셋
- 특약별 위험도 정답셋
- embedding only / topic fallback / hybrid rerank / 2차 검증 전후 근거 적합도 비교
- hallucination 감소율

### 보안/운영

실제 서비스화 단계에서 추가할 것:

- `/outputs` 정적 공개 범위 제한
- 산출물 보관 기간 정책
- 사용자별 접근 제어
- 업로드 파일 크기 제한
- 바이러스/악성 PDF 검사
- 개인정보 처리방침
- OpenAI 요청 전 민감정보 최소화
- 로그 내 개인정보 제거

### 프론트엔드 UX

보강하면 좋은 부분:

- 긴 분석 시간에 대한 단계별 진행률 표시
- 모바일 결과 화면 개선
- 하이라이트 항목 클릭 시 PDF 위치 이동
- RAG 법령 근거 접기/펼치기 개선
- 산출물 다운로드 제어

## 16. 포트폴리오에서 강조 가능한 근거

코드 근거:

- 전체 파이프라인: `backend/app/services/contract_verifier.py`
- RAG/2차 법령 검증: `backend/app/services/rag_analysis_service.py`
- PDF 하이라이트/마스킹: `backend/app/services/pdf_highlight_service.py`
- 챗봇 경로 보안: `backend/app/services/contract_chat_service.py`
- 프론트 상태 흐름: `frontend/src/context/ContractFlowProvider.tsx`

산출물 근거:

- 대표 실행 폴더: `backend/outputs/20260429_100048_5eb16df1`
- `verification_result.json`
- `rag_analysis_result.json`
- `highlighted_findings.json`
- `extraction.json`
- `highlighted.pdf`
- `highlighted.png`

수치 근거:

- 64회 실행 산출물
- `combined_result.json` 생성 60회
- `rag_analysis_result.json` 생성 59회
- 법령 2차 검증 리뷰 포함 29회
- 대표 실행 artifact 13개
- 84개 PDF 필드 위치 추출
- 16개 하이라이트 생성
- 14개 RAG 분석 항목
- 27개 법령 근거 후보 검토
- `irrelevant` 법령 후보 14개 제거
- 13개 최종 법령 근거 상세 유지
- 후보 대비 근거 제거/미채택 비율 51.9%
- 2차 검증 포함 29회 실행 합산 후보 리뷰 618개, 최종 근거 상세 247개, `irrelevant` 371개
- 29회 합산 기준 후보 대비 제거/미채택 비율 60.0%
- RAG topic 규칙 21개, query별 topic 규칙 20개, fallback topic map 24개
- 핵심 법령 6개, 조문 참조 56개, 임차인 위험 특약 60개 seed 구축

기술적 노력 근거:

- LLM JSON 응답 복구: `repair_json_text`, `extract_first_json_object`
- LLM 디버그 저장: `SAFELEASE_DEBUG_EXTRACTION`
- VWorld DOM 안정화: `wait_until_sigungu_loaded`, `wait_for_loading_to_finish`, `search_broker`
- 주소 상세 검증: `parse_leased_part`, `match_detail_items`

## 17. 면접 설명용 압축 버전

SafeLease는 임대차 계약서 PDF를 업로드하면 LLM으로 계약 내용을 구조화하고, 도로명주소 API, 중개업 조회, 임대료 통계 DB, 법령 RAG를 결합해 임차인 관점의 위험 요소를 분석하는 서비스입니다. 분석 결과는 JSON으로만 끝나지 않고 PDF 원문 좌표와 연결되어 하이라이트 PDF/PNG로 저장되며, 저장된 `combined_result.json`을 기반으로 계약서 Q&A와 임차인에게 유리한 특약 추천까지 제공합니다.

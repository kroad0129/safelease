# SafeLease 개발 포트폴리오 초안

## 1. 프로젝트 첫 페이지

**SAFELEASE**  
AI 기반 주택 임대차 계약서 검증 및 임차인 보호 리스크 분석 서비스

- 개인 프로젝트
- 개발 기간: 2026.04 ~ 2026.05
- 역할: 백엔드/AI 파이프라인/프론트엔드 구현
- 핵심 구현: PDF 계약서 구조화, 주소/중개업/임대료 검증, 법령 RAG 분석, PDF 하이라이트, 계약서 Q&A 챗봇
- Tech Stack: Python, FastAPI, OpenAI API, PostgreSQL/pgvector, Selenium, PyMuPDF, Next.js, React, TypeScript

대표 수치:

- 백엔드/프론트/RAG 시드 코드 41개 파일, 비공백 기준 약 7,346 LOC
- 백엔드 함수 217개, RAG 분석 서비스 54개 함수, PDF 하이라이트 서비스 47개 함수
- 검증 실행 산출물 64회 생성
- 4월 21일 초기 산출물은 PDF 필드 추출/하이라이트 중심, 4월 24일 RAG/combined 결과 추가, 4월 29일 2차 법령 근거 검증 결과 추가
- 대표 실행 결과 `20260429_100048_5eb16df1`: PDF 필드 84개 위치 추출, 하이라이트 16개 생성, RAG 분석 항목 14개, 법령 근거 후보 27개 2차 검증
- 2차 법령 검증으로 후보 27개 중 `irrelevant` 14개 제거, 최종 근거 상세 13개 유지
- 2차 법령 검증 산출물이 있는 29회 실행 합산 기준: 후보 리뷰 618개, 최종 근거 상세 247개, `irrelevant` 371개
- 전체 2차 검증 산출물 기준 후보 대비 약 60.0%를 부적절/중복/미채택 근거로 걸러냄
- RAG seed: 핵심 법령 6개, 조문 참조 56개, 임차인 위험 특약 60개

## 1-1. 채용 관점 핵심 차별점

SafeLease에서 가장 강하게 어필할 부분은 “AI API를 붙였다”가 아니라, **AI 결과를 신뢰 가능한 계약 검토 결과로 만들기 위해 검색 품질, 검증 근거, 개인정보, 원문 추적성까지 설계했다는 점**입니다.

차별화 포인트:

- **RAG를 embedding 유사도만으로 쓰지 않음**: topic inference, fallback topic, preferred legal refs, token overlap, primary authority bonus, noise penalty를 조합한 hybrid reranking 구현
- **근거 오염 감소 수치 제시 가능**: 대표 실행 기준 법령 후보 27개 중 14개를 `irrelevant`로 걸러 최종 근거 상세 13개만 유지, 후보 대비 51.9%를 제거/미채택
- **반복 개선 흔적 증빙 가능**: `outputs` 시간 흐름상 초기에는 하이라이트 중심이었고, 이후 combined 결과, RAG, 2차 법령 검증이 단계적으로 추가됨
- **계약서 원문 추적성 확보**: 분석 결과를 PDF field path와 연결하고, 84개 필드 좌표와 16개 하이라이트를 산출물로 생성
- **공공 검증 + AI 분석 결합**: 주소 API, 상세주소 API, VWorld 중개업 조회, 임대료 통계 DB, 법령 RAG를 하나의 파이프라인으로 연결
- **개인정보 보호 고려**: 이름, 주민등록번호, 전화번호를 JSON/PDF 산출물에서 마스킹
- **챗봇 보안 경계 구현**: 챗봇 컨텍스트는 `/outputs/.../combined_result.json`만 허용하고 path traversal 차단

면접에서 사용할 수 있는 한 줄:

> SafeLease는 LLM 요약 앱이 아니라, 계약서 PDF에서 추출한 정보를 공공 API와 통계 DB로 검증하고, RAG 검색 결과를 hybrid reranking과 2차 법령 검증으로 정제한 뒤, 최종 판단을 원문 PDF 좌표와 연결한 임대차 계약 검토 시스템입니다.

## 2. 프로젝트 개요

SafeLease는 임차인이 임대차 계약서를 업로드하면 계약서 PDF에서 주소, 보증금, 월세, 계약 기간, 중개사 정보, 특약을 추출하고 외부 공공 데이터 및 법령 RAG를 통해 위험 요소를 자동 분석하는 서비스입니다.

단순 OCR/요약이 아니라 계약서의 특정 필드가 실제 PDF 어디에 있는지 좌표로 연결하고, 검증 결과를 하이라이트 PDF와 챗봇 컨텍스트까지 이어지게 만든 것이 핵심입니다.

## 3. 담당 역할 및 구현 범위

- FastAPI 기반 계약서 검증 API 구현
- OpenAI 기반 PDF 구조화 JSON 추출 프롬프트 및 파싱 보정 구현
- 도로명주소 API로 목적물/임대인/임차인 주소 검증
- VWorld 중개업 조회 자동화로 등록번호/상호/대표자 검증
- 임대료 통계 DB 기반 환산월세 비교 로직 구현
- 법령/가이드/특약 라이브러리 RAG 검색 및 LLM 분석 구현
- LLM 2차 검증으로 부적절한 법령 근거 제거
- PyMuPDF 기반 PDF 필드 좌표 추출, 개인정보 마스킹, 하이라이트 PDF/PNG 생성
- 분석 결과 기반 계약서 Q&A 및 임차인 유리 특약 추천 챗봇 구현
- Next.js 프론트엔드 업로드, 분석 진행, 결과 확인, 챗봇 UI 구현

## 4. 백엔드 아키텍처

시스템 흐름:

Client  
-> FastAPI `/api/contracts/verify`  
-> PDF 업로드 및 LLM 구조화 추출  
-> 계약서 검증 입력 정규화  
-> 주소/상세주소 검증  
-> 중개업 등록번호 검증  
-> 임대료 참고 시세 비교  
-> 규칙 기반 finding 생성  
-> 법령/가이드/특약 RAG 검색  
-> LLM 계약조건/특약 분석  
-> LLM 2차 법령 근거 검증  
-> PDF 하이라이트 및 산출물 저장  
-> 프론트 결과 화면/챗봇

근거 코드:

- API 진입점: `backend/app/api.py`
- 검증 오케스트레이션: `backend/app/services/contract_verifier.py`
- RAG 분석: `backend/app/services/rag_analysis_service.py`
- PDF 하이라이트: `backend/app/services/pdf_highlight_service.py`
- 챗봇: `backend/app/services/contract_chat_service.py`

아키텍처에서 강조할 점:

- 단일 LLM 호출이 아니라 `추출 -> 정규화 -> 외부 검증 -> 규칙 분석 -> RAG 검색 -> LLM 분석 -> 2차 근거 검증 -> PDF 하이라이트 -> 챗봇`으로 이어지는 다단계 파이프라인입니다.
- 각 단계의 중간 산출물을 JSON으로 남겨 디버깅과 포트폴리오 증빙이 가능합니다.
- 실패 가능성이 큰 외부 요소를 분리했습니다. 주소 조회 실패, 중개업 입력 부족, RAG 실패가 각각 독립적인 status/error_code로 남습니다.

개발 과정에서 확장된 흐름:

- **2026-04-21 산출물**: `extraction.json`, `highlighted_findings.json`, `verification_result.json` 중심. PDF 필드 추출과 하이라이트 검증 단계.
- **2026-04-24 산출물**: `combined_result.json`과 `rag_analysis_result.json` 등장. 프론트/챗봇에서 재사용 가능한 통합 결과와 RAG 분석이 붙은 단계.
- **2026-04-29 산출물**: `legal_basis_reviews`가 포함되기 시작. 법령 근거를 2차로 검증하고 부적절 근거를 분리하는 단계.
- **2026-04-30 이후 산출물**: 대부분 실행에서 RAG 분석, 법령 근거 리뷰, PDF 하이라이트가 함께 생성되는 안정화 단계.

## 5. 핵심 기능 1: 계약서 PDF 구조화 및 검증 파이프라인

문제:

임대차 계약서는 금액, 날짜, 주소, 특약이 자유로운 문장과 표 안에 섞여 있어 단순 텍스트 추출만으로는 검증 API에 바로 사용할 수 없습니다.

해결:

- LLM으로 계약서를 구조화 JSON으로 추출
- 정규화 계층에서 주소, 보증금, 월세, 중개업 정보를 검증 입력 형태로 변환
- 목적물 주소, 상세 동/층/호, 임대인/임차인 주소, 중개사 등록번호, 임대료를 순차 검증
- 결과를 공통 포맷 `success | not_found | partial_match | query_failed`로 표준화

증빙:

- `verify_contract_pdf()`가 추출, 정규화, 주소 검증, 중개업 검증, 임대료 비교, finding 생성을 순서대로 수행
- 대표 산출물 `backend/outputs/20260429_100048_5eb16df1/verification_result.json`
  - 목적물 주소 검증 성공
  - 상세주소 `5층 503호` 매칭 성공
  - 임대인 주소 미조회 finding 생성

## 6. 핵심 기능 2: 임대료 참고 시세 비교

문제:

보증금과 월세가 함께 있는 계약은 단순 월세 비교가 어렵고, 같은 지역이라도 면적대에 따라 기준이 달라집니다.

해결:

- 보증금과 월세를 환산월세로 변환
- 법정동 + 면적구간 통계를 우선 사용
- 표본 수가 부족하면 시군구/면적, 법정동, 시군구 기준으로 fallback
- P75/P90 기준으로 `normal`, `slightly_high`, `high` 판정

증빙:

- 전월세전환율: 4.5%
- 법정동+면적 표본 최소 기준: 10건
- 신뢰도 기준: 표본 30건 이상 `strong`, 미만 `weak`
- 코드 위치: `backend/app/services/rent_reference_service.py`

## 7. 핵심 기능 3: 법령 RAG 및 2차 근거 검증

문제:

LLM이 법령명을 그럴듯하게 붙이면 포트폴리오나 서비스 모두에서 신뢰도가 떨어집니다. 계약서 분석에서는 “어떤 조문이 왜 이 판단의 근거인지”가 중요합니다.

해결:

- 계약조건/특약별 query item 생성
- 법령, 가이드, 유사 특약 라이브러리에서 1차 embedding 검색
- query별 topic 추론 후 관련 topic과 fallback topic으로 검색 범위 확장
- embedding 유사도만 사용하지 않고 topic 일치, 선호 조문, 토큰 겹침, 법령 원문 여부, 짧은 조문 penalty를 반영해 rerank
- 계약조건별로 우선 확인해야 하는 법령 조문을 preferred refs로 부스팅
- 1차 LLM이 분석을 생성
- 2차 LLM이 법령 후보를 `direct`, `supporting`, `irrelevant`로 재분류
- `irrelevant`는 최종 법령 근거에서 제거

RAG 성능 개선 노력:

- **Query 분해**: 계약서 전체를 한 번에 검색하지 않고 보증금, 잔금, 월 차임, 지급 방식, 기간, 목적물, 특약별 query item으로 나누어 검색 정확도를 높였습니다.
- **진단성 query 추가**: 전세/월세 체크 불명확, 보증금 합계 불일치, 잔금 구조 이상, 기간 선후 오류처럼 계약서 값에서 파생되는 위험 항목을 별도 query로 생성했습니다.
- **Topic 기반 검색 확장**: `deposit_return`, `priority_protection`, `repair_and_defect`, `broker_duty`, `pet` 등 계약 이슈별 topic을 추론하고, topic이 너무 좁아 누락되지 않도록 fallback topic을 함께 검색했습니다.
- **Hybrid reranking**: vector similarity에만 의존하지 않고 topic 일치, primary authority 여부, 법령 source 여부, query-token overlap, preferred legal refs를 점수에 더했습니다.
- **Noise penalty**: 제목성 조문이나 너무 짧은 조문, 분석 근거로 자주 섞이지만 직접 근거성이 약한 항목에는 penalty를 부여했습니다.
- **근거 압축**: LLM 입력에는 법령 3개, 가이드 3개, 유사 특약 2개 수준으로 압축해 prompt noise를 줄였습니다.
- **2차 근거 검증**: 최종 답변 전 후보 법령을 다시 검토해 직접 근거가 아닌 조문을 제거했습니다.

대표 실행 수치:

- `backend/outputs/20260429_100048_5eb16df1/rag_analysis_result.json`
- 계약조건/특약 분석 항목 14개
- 법령 근거 후보 검토 27개
- `direct` 3개, `supporting` 10개, `irrelevant` 14개로 분류
- 최종 근거 상세 13개 유지, 후보 대비 48.1%만 채택
- 후보 대비 51.9%는 부적절/중복/미채택 근거로 걸러짐
- 분석 레벨: 양호 7개, 주의 7개
- 2차 검증이 포함된 29회 실행 합산 기준 후보 리뷰 618개, 최종 근거 상세 247개, `irrelevant` 371개
- 합산 기준 후보 대비 약 60.0%를 최종 근거에서 제거/미채택

증빙 코드:

- topic 추론: `infer_topic`, `infer_topic_from_query`
- 검색 topic 확장: `build_search_topics`
- 선호 조문 부스팅: `build_preferred_legal_refs`
- rerank: `backend/app/services/rag_analysis_service.py`
- 점수 계산: `score_match`, `rerank_chunk_matches`, `rerank_clause_matches`
- 2차 법령 검증 payload 생성: `build_legal_basis_verification_payload`
- 검증 결과 적용: `apply_legal_basis_verification`

포트폴리오에 넣기 좋은 개선 포인트:

초기 RAG는 embedding 유사도만으로 조문을 붙이면 월세/잔금처럼 단어가 비슷하지만 판단 근거로는 약한 조문도 결과에 남을 수 있었습니다. 이후 query 분해, topic fallback, preferred legal refs, hybrid reranking, LLM 2차 검증을 추가해 “검색된 문서”가 아니라 “판단 근거로 쓸 수 있는 문서”만 남도록 개선했습니다.

포트폴리오 문구 예시:

> 기존 embedding-only RAG는 단어가 비슷한 조문을 근거로 붙이는 문제가 있었습니다. 이를 해결하기 위해 계약조건별 query 분해, topic fallback, preferred legal refs, token overlap 기반 reranking, LLM 2차 근거 검증을 추가했고, 대표 실행 기준 후보 법령 27개 중 14개를 부적절 근거로 제거해 최종 근거 13개만 남겼습니다.

## 8. 핵심 기능 4: PDF 하이라이트와 개인정보 마스킹

문제:

분석 결과만 보여주면 사용자가 계약서의 어느 부분이 문제인지 확인하기 어렵고, 결과물을 공유할 때 이름/주민등록번호/전화번호 노출 위험이 있습니다.

해결:

- PyMuPDF로 PDF 텍스트 레이어를 단어/라인/블록 단위로 인덱싱
- 계약서 필드별 좌표를 `bbox_0_999` 정규화 좌표로 저장
- finding/RAG 분석 결과를 원문 필드 위치와 연결
- 위험도별 색상으로 PDF annotation 생성
- 이름, 주민등록번호, 전화번호 등 민감정보 마스킹 후 저장

대표 실행 수치:

- `backend/outputs/20260429_100048_5eb16df1/extraction.json`: 필드 84개 위치 추출
- `backend/outputs/20260429_100048_5eb16df1/highlighted_findings.json`: 하이라이트 16개 생성
- 하이라이트 레벨: 주의 8개, 양호 8개

증빙 코드:

- 좌표 정규화: `rect_to_bbox_0_999`
- RAG 결과 하이라이트 연결: `add_rag_highlight_specs`
- 개인정보 마스킹: `apply_pdf_privacy_masks`
- 산출물 생성: `generate_finding_highlight_artifacts`

## 9. 핵심 기능 5: 분석 결과 기반 챗봇

문제:

계약서 분석 결과는 항목이 많아 사용자가 “그래서 내가 뭘 해야 하지?”를 바로 알기 어렵습니다.

해결:

- 저장된 `combined_result.json`만 챗봇 컨텍스트로 허용
- 경로 탈출과 임의 파일 접근 차단
- 계약 스냅샷, finding, RAG 분석 결과를 요약 컨텍스트로 구성
- 질문 topic을 추론해 법령/특약 DB에서 추가 검색
- 특약 추천 요청 시 임차인에게 유리한 문구 템플릿 제공

증빙 코드:

- 경로 검증: `resolve_output_artifact_path`
- 챗봇 응답 schema: `CHAT_OUTPUT_SCHEMA`
- 특약 추천 템플릿: `FAVORABLE_CLAUSE_TEMPLATES`
- Q&A 실행: `ask_contract_chat`

## 10. 포트폴리오에서 강조할 개선 사례

### 개선 1. 단순 LLM 요약에서 검증 가능한 계약서 분석으로 확장

- Before: 계약서 내용을 요약하는 수준이면 결과 신뢰도와 재현성이 낮음
- After: 추출 JSON, 외부 API 검증, DB 비교, RAG 근거, PDF 좌표 산출물을 모두 저장하고, 프론트/챗봇이 재사용 가능한 `combined_result.json`으로 통합
- Evidence: 초기 4회 실행에는 `combined_result.json`이 없었고, 이후 60회 실행에서 통합 산출물 생성. 대표 실행에서 13개 artifact 파일 생성

### 개선 2. 법령 RAG의 근거 오염 줄이기

- Before: embedding 유사도만으로는 관련성이 약한 법령이 분석 근거로 붙을 수 있음
- After: topic 기반 검색 확장, 선호 조문 부스팅, token overlap rerank, noise penalty, LLM 2차 검증으로 `irrelevant` 근거를 제거
- Evidence: 대표 실행에서 후보 27개 중 최종 근거 상세 13개 유지. 2차 검증 포함 29회 실행 합산 기준 후보 리뷰 618개 중 최종 근거 상세 247개 유지

### 개선 3. 검색 누락과 검색 잡음의 균형 맞추기

- Before: topic을 좁게 잡으면 필요한 근거를 놓치고, 넓게 잡으면 일반 조문이 과도하게 섞임
- After: topic별 fallback map을 두고 1차 후보는 넓게 가져온 뒤 rerank에서 topic/조문/토큰 근거로 다시 압축
- Evidence: topic 규칙 21개, query별 topic 규칙 20개, fallback topic map 24개, `build_search_topics`, `score_match`, `rerank_chunk_matches`

### 개선 4. 임차인 보호 도메인 데이터 직접 구축

- Before: 일반 법령 검색만으로는 임대차 특약 위험을 충분히 잡기 어려움
- After: 핵심 법령 6개/조문 참조 56개와 임차인 위험 특약 60개를 RAG seed로 구축
- Evidence: `rag_seed/build_seed.py`, `rag_seed/load_seed.py`

### 개선 5. 사용자가 확인 가능한 시각적 결과물 생성

- Before: JSON 결과만 있으면 사용자가 원문 위치를 다시 찾아야 함
- After: 하이라이트 PDF/PNG와 정규화 좌표 JSON을 함께 생성
- Evidence: 대표 실행에서 84개 필드 좌표, 16개 하이라이트 생성

### 개선 6. 개인정보 포함 문서의 공유 위험 완화

- Before: 계약서 원문 산출물에 이름, 주민등록번호, 전화번호가 노출될 수 있음
- After: PDF 저장 단계에서 민감정보 위치를 찾아 redaction 및 대체 텍스트 삽입
- Evidence: `privacy_masking.py`, `apply_pdf_privacy_masks`

### 개선 7. 챗봇 컨텍스트 접근 범위 제한

- Before: 파일 경로를 직접 받으면 경로 탈출 위험 발생 가능
- After: `/outputs/.../combined_result.json`만 허용하고, resolved path가 `OUTPUT_DIR` 하위인지 확인
- Evidence: `resolve_output_artifact_path`

### 개선 8. LLM 출력 파싱 안정성 보강

- Before: LLM 응답이 코드블록, 앞뒤 설명, 잘못된 escape를 포함하면 JSON 파싱이 실패할 수 있음
- After: 첫 JSON 객체 추출, 코드블록 제거, escape 보정, `SAFELEASE_DEBUG_EXTRACTION=1`일 때 원문/복구 JSON 저장
- Evidence: `repair_json_text`, `extract_first_json_object`, `SAFELEASE_DEBUG_EXTRACTION`

### 개선 9. 외부 사이트 자동화 안정성 보강

- Before: VWorld 중개업 조회는 DOM 로딩, select option 지연, stale element, loading overlay 때문에 자동화가 불안정할 수 있음
- After: headless Chrome, select option polling, loading overlay wait, 결과 table wait, retryable DOM error 최대 3회 재시도 구현
- Evidence: `broker_validator.py`의 `wait_until_sigungu_loaded`, `wait_for_loading_to_finish`, `parse_result_from_dom`, `search_broker`

### 개선 10. 주소 검증을 기본주소와 상세주소로 분리

- Before: 주소 문자열만 맞으면 실제 호실 존재 여부까지 확인하기 어려움
- After: 도로명주소 검색 후 동/층/호를 파싱해 상세주소 API 결과와 비교하고, 기본주소 성공/상세주소 미확인/상세주소 불일치를 다른 상태로 분리
- Evidence: `address_validator.py`의 `parse_leased_part`, `match_detail_items`, `partial_match`, `DETAIL_VALUE_NOT_FOUND`

## 10-1. 이력서/면접용 성과 문장

- 임대차 계약서 PDF 검증 파이프라인을 18단계로 설계하고, 추출/검증/RAG/하이라이트/챗봇까지 end-to-end 구현했습니다.
- embedding-only RAG의 근거 오염 문제를 줄이기 위해 topic fallback, preferred legal refs, token overlap 기반 hybrid reranking, 2차 LLM 근거 검증을 적용했습니다.
- 대표 실행 기준 법령 후보 27개를 검토해 `irrelevant` 14개를 제거하고 최종 근거 상세 13개만 유지하도록 개선했습니다.
- 2차 법령 검증이 포함된 29회 실행 합산 기준 후보 리뷰 618개 중 최종 근거 상세 247개를 유지해, 약 60.0%의 후보를 부적절/중복/미채택 근거로 걸러냈습니다.
- 계약서 분석 결과를 원문 PDF 좌표와 연결해 84개 필드 좌표와 16개 하이라이트를 생성, 사용자가 AI 판단 근거를 원문에서 확인할 수 있게 했습니다.
- 도로명주소 API, VWorld 중개업 조회, 임대료 통계 DB, 법령 RAG를 통합해 단순 요약이 아닌 검증 가능한 계약 검토 결과를 제공했습니다.
- 이름/주민등록번호/전화번호 마스킹과 챗봇 컨텍스트 path traversal 차단을 구현해 민감 문서 처리 시 필요한 보안 경계를 반영했습니다.
- LLM JSON 파싱 실패에 대비해 응답 복구 로직과 디버그 저장 옵션을 구현했고, 외부 사이트 자동화에는 DOM retry와 loading wait를 적용했습니다.

## 11. 면접에서 말하기 좋은 한 문장

SafeLease는 계약서 PDF를 단순 요약하는 서비스가 아니라, LLM 추출 결과를 공공 API/통계 DB/RAG 법령 근거와 결합하고, 최종 판단을 원문 PDF 좌표와 연결해 사용자가 직접 검증 가능한 형태로 만든 임대차 계약 검토 시스템입니다.

## 12. 보완하면 좋은 부분

- 테스트 코드 보강: 현재는 smoke check와 실행 산출물 중심이라 단위 테스트/통합 테스트가 더 있으면 좋음
- RAG 평가셋 추가: 법령 근거 정답셋을 만들어 근거 적합도 개선 수치를 더 명확히 제시 가능
- 개인정보 보관 정책: `/outputs` 공개 범위, 보관 기간, 삭제 정책을 서비스 요구사항으로 명시 필요
- 프론트 사용성 증빙: 실제 업로드부터 결과/챗봇까지 화면 캡처를 넣으면 완성도가 올라감

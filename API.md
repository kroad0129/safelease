# SafeLease API

[프로젝트 README](../README.md) · [아키텍처](ARCHITECTURE.md) · [백엔드 상세 문서](../backend/README.md)

SafeLease 백엔드는 FastAPI로 구현되어 있습니다. 기본 주소는 `http://127.0.0.1:8000`이며, 서버 실행 후 `/docs`에서 OpenAPI UI를 확인할 수 있습니다.

## 공통 동작

- 응답 본문은 JSON이며 오류는 FastAPI 기본 형식인 `{"detail": "오류 메시지"}`로 반환합니다.
- 인증 헤더와 사용자 세션은 사용하지 않습니다.
- 분석 요청은 동기식입니다. `POST /api/contracts/verify` 연결이 유지되는 동안 전체 파이프라인이 실행됩니다.
- CORS 허용 origin은 `http://localhost:3000`, `http://127.0.0.1:3000`입니다.

## 엔드포인트

| Method | Endpoint | 설명 |
|---|---|---|
| `GET` | `/health` | 서버 상태 확인 |
| `POST` | `/api/contracts/verify` | PDF 계약서 분석 |
| `GET` | `/api/contracts/history` | 분석 기록 목록 |
| `GET` | `/api/contracts/history/{history_id}` | 분석 기록 상세 |
| `POST` | `/api/contracts/chat` | 분석 결과 기반 질의응답 |

## `GET /health`

프로세스가 요청에 응답할 수 있는지만 확인합니다. DB, OpenAI, 주소 API, Chrome 상태까지 검사하는 readiness check는 아닙니다.

```json
{
  "status": "ok"
}
```

## `POST /api/contracts/verify`

PDF를 업로드해 구조화 추출, 외부 검증, 규칙 판정, 법령 RAG, PDF 하이라이트를 순서대로 실행합니다.

### Request

- Content-Type: `multipart/form-data`
- Field: `file`
- 코드상 조건: 파일명이 `.pdf`로 끝나며 파일 크기가 0이 아닐 것

```bash
curl -X POST http://127.0.0.1:8000/api/contracts/verify \
  -F "file=@virtual-contract.pdf;type=application/pdf"
```

### 내부 호출

```text
api.verify_contract
└─ contract_service.verify_contract_upload_stream
   ├─ 임시 PDF 저장
   ├─ contract_verifier.verify_contract_pdf
   │  ├─ OpenAI 파일 업로드와 구조화 추출
   │  ├─ 검증 입력 정규화
   │  ├─ 주소·중개업·임대료 검증
   │  └─ 규칙 기반 finding 생성
   ├─ verification_persistence.persist_verification_outputs
   │  ├─ RAG 검색과 분석
   │  ├─ PDF 좌표·하이라이트 생성
   │  └─ 마스킹된 결과 저장
   └─ 임시 PDF 삭제
```

### Response `200 OK`

```json
{
  "result": {
    "extracted": {},
    "verification": {},
    "rag_analysis": {},
    "highlight_summary": {}
  },
  "outputPaths": {
    "run_dir": "..."
  },
  "artifacts": {
    "highlightedPdfUrl": "/outputs/{run_id}/highlighted.pdf",
    "highlightedImageUrl": "/outputs/{run_id}/highlighted.png",
    "renderedImageUrl": "/outputs/{run_id}/rendered.png",
    "extractionJsonUrl": "/outputs/{run_id}/extraction.json",
    "highlightJsonUrl": "/outputs/{run_id}/highlighted_findings.json",
    "analysisJsonUrl": "/outputs/{run_id}/analysis_result.json",
    "verificationJsonUrl": "/outputs/{run_id}/verification_result.json",
    "combinedResultJsonUrl": "/outputs/{run_id}/combined_result.json",
    "ragResultJsonUrl": "/outputs/{run_id}/rag_result.json",
    "ragPayloadJsonUrl": "/outputs/{run_id}/rag_llm_payload.json",
    "ragAnalysisJsonUrl": "/outputs/{run_id}/rag_analysis_result.json"
  },
  "highlightSummary": {},
  "review": {
    "headline": "몇 가지 확인이 더 필요한 계약서입니다.",
    "reviewLevel": "보통",
    "reviewText": "...",
    "findingCount": 2,
    "passedChecks": [],
    "inputSummary": {}
  },
  "ragAnalysis": {
    "status": "success",
    "embeddingModel": "text-embedding-3-small",
    "analysisModel": "gpt-5.4-mini",
    "summary": {}
  },
  "ragReview": {}
}
```

산출물 생성 여부에 따라 일부 URL은 `null`일 수 있습니다. RAG 전체 단계가 실패하면 `ragAnalysis.status`는 `failed`가 되고 `errorMessage`가 포함되지만 앞서 생성된 기본 검증 결과는 유지됩니다.

### Errors

| Status | 조건 |
|---|---|
| `400` | 파일명이 `.pdf`로 끝나지 않거나 파일이 비어 있음 |
| `400` | 처리 중 `FileNotFoundError` 또는 `ValueError` 발생 |
| `422` | `file` 필드 누락 또는 요청 검증 실패 |
| `500` | 그 밖의 분석 예외 |

현재 MIME type, 최대 파일 크기, PDF 페이지 수는 검증하지 않습니다.

## `GET /api/contracts/history`

`backend/outputs`의 하위 디렉터리를 최신 이름순으로 순회하고, `combined_result.json`을 읽을 수 있는 기록만 반환합니다. pagination은 없습니다.

```json
{
  "items": [
    {
      "id": "20260514_153012_ab12cd34",
      "label": "서울시 강서구 ... / 5층 503호 전부",
      "createdAt": 1778740212.34,
      "reviewLevel": "보통",
      "findingCount": 3,
      "hasHighlight": true,
      "hasChatContext": true
    }
  ]
}
```

주소와 임대할 부분이 없으면 디렉터리 이름을 `label`로 사용합니다. `createdAt`은 디렉터리 수정 시각의 Unix timestamp입니다.

## `GET /api/contracts/history/{history_id}`

저장된 결과를 읽어 verify API와 같은 응답 구조로 복원합니다. ID는 다음 형식이어야 합니다.

```regex
^\d{8}_\d{6}_[a-f0-9]+$
```

예: `20260514_153012_ab12cd34`

| Status | 조건 |
|---|---|
| `400` | ID 형식 불일치 또는 outputs 밖의 경로 |
| `404` | 기록 디렉터리나 `combined_result.json`이 없음 |
| `500` | 저장된 JSON을 파싱할 수 없음 |

## `POST /api/contracts/chat`

저장된 `combined_result.json`과 질문별 RAG 검색 결과로 답변을 생성합니다.

### Request

```json
{
  "combined_result_url": "/outputs/20260514_153012_ab12cd34/combined_result.json",
  "question": "보증금 반환과 관련해 확인할 내용이 있어?",
  "history": [
    {
      "role": "user",
      "content": "이 계약서에서 가장 중요한 위험은 뭐야?"
    },
    {
      "role": "assistant",
      "content": "..."
    }
  ]
}
```

`history`를 생략하면 빈 배열로 처리합니다. `role` enum 제한과 질문 길이 제한은 현재 없습니다.

### 허용 파일

`combined_result_url`은 다음 조건을 모두 충족해야 합니다.

1. `/outputs/`로 시작
2. 실제 경로가 `backend/outputs` 내부
3. 파일명이 정확히 `combined_result.json`
4. 파일이 존재

### Response `200 OK`

```json
{
  "intent": "risk_question",
  "answer": "...",
  "related_contract_points": [],
  "recommended_clauses": [],
  "legal_basis": [
    {
      "basis": "주택임대차보호법 제3조",
      "title": "...",
      "text": "...",
      "relevance": "direct"
    }
  ],
  "cautions": [],
  "follow_up_questions": []
}
```

`intent`는 `analysis_explanation`, `risk_question`, `clause_recommendation`, `legal_question`, `rewrite_request`, `general` 중 하나입니다.

| Status | 조건 |
|---|---|
| `400` | 결과 URL, 허용 경로 또는 파일명 검증 실패 |
| `404` | 지정한 결과 파일이 없음 |
| `422` | 요청 필드 누락 또는 타입 불일치 |
| `500` | OpenAI, DB 검색 또는 응답 생성 예외 |

## 정적 산출물 `/outputs/*`

FastAPI는 `backend/outputs`를 `/outputs`에 정적으로 mount합니다. artifact URL에서 JSON, PNG, PDF를 받을 수 있습니다.

현재 이 경로에는 인증과 사용자별 권한 확인이 없습니다. 운영 환경에서는 권한 검사를 수행하는 다운로드 API와 만료 정책으로 교체해야 합니다.

import json
import re
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.core.common import OUTPUT_DIR
from app.presenters import build_verify_response_payload, build_verify_response_payload_from_public_result
from app.services.contract_chat_service import ask_contract_chat
from app.services.contract_service import verify_contract_upload_stream


app = FastAPI(title="SafeLease API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")


class ChatHistoryItem(BaseModel):
    role: str
    content: str


class ContractChatRequest(BaseModel):
    combined_result_url: str
    question: str
    history: list[ChatHistoryItem] = Field(default_factory=list)


HISTORY_ID_RE = re.compile(r"^\d{8}_\d{6}_[a-f0-9]+$")


def _build_history_output_paths(run_dir: Path) -> dict:
    path_map = {
        "run_dir": run_dir,
        "extracted_output_path": run_dir / "extracted_contract.json",
        "verification_output_path": run_dir / "verification_result.json",
        "analysis_output_path": run_dir / "analysis_result.json",
        "combined_output_path": run_dir / "combined_result.json",
        "highlighted_pdf_path": run_dir / "highlighted.pdf",
        "rendered_png_path": run_dir / "rendered.png",
        "highlighted_png_path": run_dir / "highlighted.png",
        "highlight_json_path": run_dir / "highlighted_findings.json",
        "rag_result_path": run_dir / "rag_result.json",
        "rag_payload_path": run_dir / "rag_llm_payload.json",
        "rag_analysis_path": run_dir / "rag_analysis_result.json",
    }
    return {key: str(path) for key, path in path_map.items() if key == "run_dir" or path.exists()}


def _load_combined_result(run_dir: Path) -> dict:
    combined_path = run_dir / "combined_result.json"
    if not combined_path.exists():
        raise FileNotFoundError("저장된 통합 분석 결과가 없습니다.")
    with combined_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _history_label(public_result: dict, fallback: str) -> str:
    input_summary = ((public_result.get("verification") or {}).get("input_summary") or {})
    property_summary = input_summary.get("property") if isinstance(input_summary, dict) else {}
    address = property_summary.get("address") if isinstance(property_summary, dict) else None
    leased_part = property_summary.get("leased_part_raw") if isinstance(property_summary, dict) else None
    label_parts = [part for part in (address, leased_part) if part]
    return " / ".join(label_parts) if label_parts else fallback


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@app.get("/api/contracts/history")
def list_contract_history() -> dict:
    records = []
    if not OUTPUT_DIR.exists():
        return {"items": records}

    for run_dir in sorted((item for item in OUTPUT_DIR.iterdir() if item.is_dir()), reverse=True):
        try:
            public_result = _load_combined_result(run_dir)
        except (FileNotFoundError, json.JSONDecodeError):
            continue

        summary = ((public_result.get("verification") or {}).get("analysis") or {}).get("summary") or {}
        records.append(
            {
                "id": run_dir.name,
                "label": _history_label(public_result, run_dir.name),
                "createdAt": run_dir.stat().st_mtime,
                "reviewLevel": summary.get("review_level"),
                "findingCount": summary.get("finding_count", 0),
                "hasHighlight": (run_dir / "highlighted.png").exists() or (run_dir / "highlighted.pdf").exists(),
                "hasChatContext": (run_dir / "combined_result.json").exists(),
            }
        )

    return {"items": records}


@app.get("/api/contracts/history/{history_id}")
def get_contract_history(history_id: str) -> dict:
    if not HISTORY_ID_RE.match(history_id):
        raise HTTPException(status_code=400, detail="올바르지 않은 검토 기록 ID입니다.")

    run_dir = (OUTPUT_DIR / history_id).resolve()
    try:
        run_dir.relative_to(OUTPUT_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="올바르지 않은 검토 기록 경로입니다.") from exc

    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="검토 기록을 찾을 수 없습니다.")

    try:
        public_result = _load_combined_result(run_dir)
        return build_verify_response_payload_from_public_result(
            public_result,
            _build_history_output_paths(run_dir),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="저장된 분석 결과 JSON을 읽을 수 없습니다.") from exc


@app.post("/api/contracts/verify")
async def verify_contract(file: UploadFile = File(...)) -> dict:
    filename = file.filename or ""

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")

    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size == 0:
        raise HTTPException(status_code=400, detail="업로드된 파일이 비어 있습니다.")

    try:
        result = verify_contract_upload_stream(filename=filename, file_obj=file.file)
        return build_verify_response_payload(result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"검증 처리 중 오류가 발생했습니다: {exc}") from exc


@app.post("/api/contracts/chat")
async def contract_chat(request: ContractChatRequest) -> dict:
    try:
        return ask_contract_chat(
            combined_result_url=request.combined_result_url,
            question=request.question,
            history=[item.dict() for item in request.history],
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"챗봇 답변 생성 중 오류가 발생했습니다: {exc}") from exc

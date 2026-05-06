from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.core.common import OUTPUT_DIR
from app.presenters import build_verify_response_payload
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


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


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

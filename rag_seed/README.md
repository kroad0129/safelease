# SafeLease RAG Seed Tools

임대차 RAG DB를 보강하기 위한 별도 작업 폴더입니다. 기존 `backend/app` 코드를 직접 섞지 않고,
법령 수집 결과와 임차인 보호 중심 위험 특약 라이브러리를 만든 뒤 기존 PostgreSQL RAG 테이블에 적재합니다.

## Files

- `build_seed.py`: 국가법령정보센터 API에서 핵심 조문을 수집하고, 임차인 보호 중심 특약 seed를 생성합니다.
- `load_seed.py`: `dist/*.jsonl`을 기존 DB의 `source_documents`, `source_chunks`, `clause_library`와 embedding 테이블에 upsert합니다.
- `dist/`: 생성 결과가 저장되는 폴더입니다. 실행 전에는 없어도 됩니다.

## Run

```powershell
$env:LAW_API_OC="your-oc"
python rag_seed\build_seed.py
python rag_seed\load_seed.py
```

`load_seed.py`는 `backend/.env`의 DB/OpenAI 설정을 사용합니다.

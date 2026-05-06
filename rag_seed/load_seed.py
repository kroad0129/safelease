import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import psycopg
from openai import OpenAI

from app.services.rag_analysis_service import DEFAULT_EMBEDDING_MODEL, get_connection_string, get_openai_client, vector_literal


DEFAULT_INPUT_DIR = Path(__file__).resolve().parent / "dist"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def embed_texts(client: OpenAI, model: str, texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    batch_size = 100
    for start in range(0, len(texts), batch_size):
        response = client.embeddings.create(model=model, input=texts[start:start + batch_size])
        vectors.extend(item.embedding for item in response.data)
    return vectors


def text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def upsert_documents(cur: psycopg.Cursor[Any], rows: list[dict[str, Any]]) -> None:
    for row in rows:
        cur.execute(
            """
            insert into source_documents (
                document_id, source_type, source_name, title, raw_text, normalized_text, metadata_json
            ) values (
                %(document_id)s, %(source_type)s, %(source_name)s, %(title)s, %(raw_text)s, %(normalized_text)s, %(metadata_json)s::jsonb
            )
            on conflict (document_id) do update set
                source_type = excluded.source_type,
                source_name = excluded.source_name,
                title = excluded.title,
                raw_text = excluded.raw_text,
                normalized_text = excluded.normalized_text,
                metadata_json = excluded.metadata_json
            """,
            {**row, "metadata_json": json.dumps(row.get("metadata_json") or {}, ensure_ascii=False)},
        )


def upsert_chunks(cur: psycopg.Cursor[Any], rows: list[dict[str, Any]]) -> None:
    for row in rows:
        cur.execute(
            """
            insert into source_chunks (
                chunk_id, document_id, source_type, source_name, title, chunk_text, normalized_text,
                embedding_text, topic, subtopic, reliability, audience, law_name, law_id, article_uid,
                article_no, article_branch_no, is_primary_authority, metadata_json
            ) values (
                %(chunk_id)s, %(document_id)s, %(source_type)s, %(source_name)s, %(title)s, %(chunk_text)s, %(normalized_text)s,
                %(embedding_text)s, %(topic)s, %(subtopic)s, %(reliability)s, %(audience)s, %(law_name)s, %(law_id)s, %(article_uid)s,
                %(article_no)s, %(article_branch_no)s, %(is_primary_authority)s, %(metadata_json)s::jsonb
            )
            on conflict (chunk_id) do update set
                document_id = excluded.document_id,
                source_type = excluded.source_type,
                source_name = excluded.source_name,
                title = excluded.title,
                chunk_text = excluded.chunk_text,
                normalized_text = excluded.normalized_text,
                embedding_text = excluded.embedding_text,
                topic = excluded.topic,
                subtopic = excluded.subtopic,
                reliability = excluded.reliability,
                audience = excluded.audience,
                law_name = excluded.law_name,
                law_id = excluded.law_id,
                article_uid = excluded.article_uid,
                article_no = excluded.article_no,
                article_branch_no = excluded.article_branch_no,
                is_primary_authority = excluded.is_primary_authority,
                metadata_json = excluded.metadata_json
            """,
            {**row, "metadata_json": json.dumps(row.get("metadata_json") or {}, ensure_ascii=False)},
        )


def upsert_clauses(cur: psycopg.Cursor[Any], rows: list[dict[str, Any]]) -> None:
    for row in rows:
        cur.execute(
            """
            insert into clause_library (
                library_clause_id, source_chunk_id, source_type, source_name, title, raw_text,
                normalized_text, topic, label_type, perspective, favorability, risk_level,
                legality_status, embedding_text, metadata_json
            ) values (
                %(library_clause_id)s, %(source_chunk_id)s, %(source_type)s, %(source_name)s, %(title)s, %(raw_text)s,
                %(normalized_text)s, %(topic)s, %(label_type)s, %(perspective)s, %(favorability)s, %(risk_level)s,
                %(legality_status)s, %(embedding_text)s, %(metadata_json)s::jsonb
            )
            on conflict (library_clause_id) do update set
                source_chunk_id = excluded.source_chunk_id,
                source_type = excluded.source_type,
                source_name = excluded.source_name,
                title = excluded.title,
                raw_text = excluded.raw_text,
                normalized_text = excluded.normalized_text,
                topic = excluded.topic,
                label_type = excluded.label_type,
                perspective = excluded.perspective,
                favorability = excluded.favorability,
                risk_level = excluded.risk_level,
                legality_status = excluded.legality_status,
                embedding_text = excluded.embedding_text,
                metadata_json = excluded.metadata_json
            """,
            {**row, "metadata_json": json.dumps(row.get("metadata_json") or {}, ensure_ascii=False)},
        )


def upsert_source_embeddings(cur: psycopg.Cursor[Any], rows: list[dict[str, Any]], vectors: list[list[float]], model: str) -> None:
    for row, vector in zip(rows, vectors):
        cur.execute(
            """
            insert into source_chunk_embeddings (chunk_id, embedding_model, embedding, embedded_text_hash)
            values (%s, %s, %s::vector, %s)
            on conflict (chunk_id, embedding_model) do update set
                embedding = excluded.embedding,
                embedded_text_hash = excluded.embedded_text_hash
            """,
            (row["chunk_id"], model, vector_literal(vector), text_hash(row.get("embedding_text", ""))),
        )


def upsert_clause_embeddings(cur: psycopg.Cursor[Any], rows: list[dict[str, Any]], vectors: list[list[float]], model: str) -> None:
    for row, vector in zip(rows, vectors):
        cur.execute(
            """
            insert into clause_library_embeddings (library_clause_id, embedding_model, embedding, embedded_text_hash)
            values (%s, %s, %s::vector, %s)
            on conflict (library_clause_id, embedding_model) do update set
                embedding = excluded.embedding,
                embedded_text_hash = excluded.embedded_text_hash
            """,
            (row["library_clause_id"], model, vector_literal(vector), text_hash(row.get("embedding_text", ""))),
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--skip-embeddings", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)
    documents = load_jsonl(input_dir / "source_documents.jsonl")
    chunks = load_jsonl(input_dir / "source_chunks.jsonl")
    clauses = load_jsonl(input_dir / "tenant_risk_clauses.jsonl")

    client = None if args.skip_embeddings else get_openai_client()
    chunk_vectors = []
    clause_vectors = []
    if client:
        chunk_vectors = embed_texts(client, args.embedding_model, [row["embedding_text"] for row in chunks])
        clause_vectors = embed_texts(client, args.embedding_model, [row["embedding_text"] for row in clauses])

    with psycopg.connect(get_connection_string()) as conn:
        with conn.cursor() as cur:
            upsert_documents(cur, documents)
            upsert_chunks(cur, chunks)
            upsert_clauses(cur, clauses)
            if client:
                upsert_source_embeddings(cur, chunks, chunk_vectors, args.embedding_model)
                upsert_clause_embeddings(cur, clauses, clause_vectors, args.embedding_model)
        conn.commit()

    print(json.dumps({"documents": len(documents), "chunks": len(chunks), "clauses": len(clauses), "embeddings": not args.skip_embeddings}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

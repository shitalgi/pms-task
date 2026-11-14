# Palm Mind AI — Document RAG and Interview Booking API

A backend-only FastAPI project for ingesting PDF/TXT documents, retrieving relevant passages with Qdrant, answering with OpenAI, and handling interview bookings in a multi-turn chat. It does not use a prebuilt `RetrievalQAChain`, FAISS, Chroma, or a frontend.

## Features

- `POST /api/v1/documents/ingest`: extract PDF or UTF-8 TXT text, split it using `fixed` or `recursive` chunking, create OpenAI embeddings, index chunks in Qdrant, and store metadata in SQL.
- `GET /api/v1/documents`: list SQL document metadata.
- `POST /api/v1/chat`: custom retrieval + prompt construction + OpenAI generation; returns answer and source passages.
- Independent `session_id` histories and booking drafts stored in Redis with a configurable expiry.
- Interview booking workflow detects intent with the LLM, collects and validates name/email/date/time, asks for explicit confirmation, then persists confirmed bookings in SQL.
- OpenAPI/Swagger documentation at `/docs`.

## Architecture

```text
FastAPI routes
  ├── DocumentService ── PyMuPDF / chunkers ── OpenAI embeddings ── Qdrant
  │                                                   └──────────── SQLAlchemy metadata
  └── RAGService ── Redis history ── LLM booking intent
       ├── BookingService ── Redis draft + SQL booking
       └── OpenAI query embedding ── Qdrant search ── custom answer prompt ── OpenAI chat
```

### Project structure

```text
app/
  api/
    dependencies.py
    routes/
      chat.py
      documents.py
  core/
    config.py
    database.py
    logging.py
  models/
    base.py
    booking.py
    document.py
  repositories/
    bookings.py
    documents.py
  schemas/
    bookings.py
    chat.py
    documents.py
  services/
    bookings.py
    chunking.py
    documents.py
    llm.py
    memory.py
    rag.py
    vector_store.py
  main.py
tests/
  conftest.py
  test_api.py
  test_bookings.py
  test_chunking.py
  test_documents.py
Dockerfile
docker-compose.yml
requirements.txt
```

## Requirements and configuration

- Python 3.11+
- Docker Desktop with Docker Compose (recommended for Qdrant and Redis)
- An OpenAI API key for actual embedding and generation calls

Create a local environment file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set `OPENAI_API_KEY`. The key is intentionally not committed. SQLite, Qdrant, and Redis have local defaults. You can change model names, vector dimensions, database URL, upload size, chunk size/overlap, chat-history length, and TTL with environment variables.

## Run with Docker Compose (recommended)

```powershell
docker compose up --build
```

Compose starts the API, Qdrant, and Redis. The API is at `http://localhost:8000`; Swagger UI is at `http://localhost:8000/docs`. Data is persisted in the `app_data` and `qdrant_data` Docker volumes.

Stop the services with `Ctrl+C`, or run `docker compose down`. To remove persisted data too, run `docker compose down -v`.

## Run the API locally

Run Qdrant and Redis with Compose, then run the Python API outside Compose:

```powershell
Copy-Item .env.example .env
# Add OPENAI_API_KEY to .env
docker compose up -d qdrant redis
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

If PowerShell blocks activation, use `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`.

## API usage

### 1. Ingest a document

Request (PowerShell):

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/documents/ingest?chunking_strategy=recursive" `
  -F "file=@.\handbook.pdf"
```

Use `chunking_strategy=fixed` for fixed-size chunks with overlap. The default is `recursive`. Only `.pdf` and UTF-8 `.txt` files are accepted. Uploads are limited by `MAX_UPLOAD_SIZE_MB`.

Example response:

```json
{
  "document_id": "1ab6a7ed-c786-4fea-8c30-1a38c26209a5",
  "filename": "handbook.pdf",
  "chunking_strategy": "recursive",
  "chunk_count": 8,
  "character_count": 5362,
  "processing_time_seconds": 1.42,
  "status": "processed"
}
```

List indexed metadata:

```powershell
curl.exe "http://localhost:8000/api/v1/documents?limit=50&offset=0"
```

### 2. Ask questions / book an interview

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/chat" `
  -H "Content-Type: application/json" `
  -d '{\"message\":\"What does the handbook say about leave?\",\"session_id\":\"candidate-123\",\"top_k\":5}'
```

Example RAG response:

```json
{
  "session_id": "candidate-123",
  "answer": "The handbook says employees should submit leave requests to their manager.",
  "sources": [
    {
      "document_id": "1ab6a7ed-c786-4fea-8c30-1a38c26209a5",
      "filename": "handbook.pdf",
      "chunk_index": 3,
      "score": 0.83,
      "text": "Employees should submit leave requests to their manager..."
    }
  ],
  "intent": "question",
  "booking_id": null
}
```

Pass the same `session_id` to keep using its history; a new ID starts an independent conversation. If omitted, the API creates one and returns it. Chat history is bounded by `CHAT_HISTORY_TURNS` and expires after `CHAT_MEMORY_TTL_SECONDS`.

Example interview-booking exchange:

```json
{"message":"I want to book an interview","session_id":"booking-42"}
```

The assistant asks for missing name, email, date (`YYYY-MM-DD`), and time (`HH:MM`). When all are present, it repeats the details and asks for confirmation. Only an explicit yes after that summary saves the record. A no/cancel discards the draft.

Successful final response:

```json
{
  "session_id": "booking-42",
  "answer": "Your interview is booked for 2027-01-15 at 14:30. Confirmation ID: 55e3c9a8-...",
  "sources": [],
  "intent": "booking",
  "booking_id": "55e3c9a8-..."
}
```

## Database and service details

- SQLAlchemy tables: `documents` and `interview_bookings`; SQLite is the local default, and `DATABASE_URL` can point at PostgreSQL when its driver is installed/configured.
- Qdrant payloads include the SQL document ID, filename, chunk index, and text; vector dimensions are set using `EMBEDDING_DIMENSIONS`.
- OpenAI embedding responses are paired with source text; Qdrant search results are included with answer responses.
- Booking date/time strings are normalized and checked, email is validated, and dates must be future dates. SQL persistence happens only after confirmation.
- Scanned/image-only PDFs without an embedded text layer are rejected as having no readable text; OCR is intentionally outside this assignment.
- The default error responses use standard HTTP validation codes. Missing OpenAI configuration/provider failures return a service error rather than a fabricated answer.

## Tests

Install dependencies, then run:

```powershell
pytest -q
```

Tests use fake OpenAI/Qdrant/Redis adapters and in-memory SQLite, so they do not require credentials or running external services. They cover chunking, PDF/TXT handling, SQL persistence, endpoint validation, source responses, and the explicit booking-confirmation boundary.

## GitHub submission

Initialize and push from the project directory (replace the URL with your own empty GitHub repository):

```powershell
git init
git add .
git commit -m "Build Palm Mind AI RAG backend"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/palm-mind-rag-backend.git
git push -u origin main
```

Do not add `.env` or database files. `.gitignore` excludes these.

## Requirement checklist

- [x] FastAPI backend with ingestion and conversational endpoints
- [x] PDF/TXT extraction, validation, and processing response
- [x] Fixed-size overlap and recursive chunking
- [x] OpenAI embeddings, Qdrant vector storage, and SQL metadata
- [x] Custom retrieval + prompt-based generation (no `RetrievalQAChain`)
- [x] Redis multi-turn history and separate session IDs
- [x] Relevant source chunks returned to clients
- [x] LLM-assisted booking intent and multi-turn detail collection
- [x] Name, email, future date, and time validation
- [x] Explicit confirmation required before SQL booking insert
- [x] Modular routers, services, repositories, schemas, and models
- [x] Environment configuration, logging, errors, tests, Docker, and Swagger
- [x] No FAISS, Chroma, or frontend

## Potential interview questions

1. **Why store metadata in SQL and embeddings in Qdrant?** SQL provides reliable structured records and constraints; Qdrant provides vector similarity search. Each store is used for the query type it handles well.
2. **How does custom RAG work here?** Embed the question, search Qdrant for top-k chunks, build a context prompt with conversation history, call the chat model, and return source payloads alongside the answer.
3. **Why use chunk overlap?** It reduces the chance that a sentence or concept split at a boundary loses useful context. Overlap also increases index size, so it should be tuned to the document and model.
4. **What is recursive splitting?** It tries natural boundaries (paragraphs, lines, then smaller separators) before falling back to character-level splitting, while respecting the configured maximum chunk size.
5. **How is conversation state isolated?** Redis keys include the caller's `session_id`; history and booking draft keys are distinct and expire via TTL.
6. **How do you prevent accidental bookings?** The assistant stores a draft, presents a normalized summary, and only writes the SQL row after a subsequent explicit confirmation.
7. **What consistency issue exists across SQL and Qdrant?** They do not share a transaction. The ingestion path deletes Qdrant points if SQL persistence fails. A production system may add an outbox/reconciliation process for crash-safe recovery.
8. **How would you productionize this further?** Add authentication/rate limiting, migrations, observability and tracing, asynchronous ingestion jobs, idempotency, stronger booking time-zone/business-hour rules, and retry/reconciliation for external services.

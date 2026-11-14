from datetime import date, timedelta

from app.models.booking import InterviewBooking


def test_document_ingestion_endpoint_and_invalid_file(app_client) -> None:
    response = app_client.post(
        "/api/v1/documents/ingest?chunking_strategy=fixed",
        files={"file": ("notes.txt", b"Palm Mind AI creates applied AI software.", "text/plain")},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "processed"
    assert payload["chunk_count"] > 0

    listed = app_client.get("/api/v1/documents")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["documents"][0]["id"] == payload["document_id"]

    invalid = app_client.post(
        "/api/v1/documents/ingest",
        files={"file": ("photo.jpg", b"not supported", "image/jpeg")},
    )
    assert invalid.status_code == 422


def test_swagger_openapi_includes_both_api_groups(app_client) -> None:
    response = app_client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/documents/ingest" in paths
    assert "/api/v1/chat" in paths


def test_chat_endpoint_returns_answer_and_sources(app_client) -> None:
    response = app_client.post(
        "/api/v1/chat",
        json={"message": "What does Palm Mind AI build?", "session_id": "test-session"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "test-session"
    assert payload["intent"] == "question"
    assert payload["sources"][0]["filename"] == "handbook.txt"
    assert "Palm Mind AI builds" in payload["answer"]


def test_chat_validates_top_k(app_client) -> None:
    response = app_client.post("/api/v1/chat", json={"message": "hello", "top_k": 0})
    assert response.status_code == 422


def test_chat_booking_requires_confirmation_and_then_saves(app_client) -> None:
    class BookingLLM:
        async def extract_booking_fields(self, message, history):
            if message == "book it":
                return {
                    "intent": "booking",
                    "full_name": "Avery Example",
                    "email": "avery@example.com",
                    "interview_date": (date.today() + timedelta(days=5)).isoformat(),
                    "interview_time": "14:30",
                    "confirmation": None,
                    "cancel": False,
                }
            return {"intent": "question", "confirmation": True, "cancel": False}

    app_client.app.state.llm = BookingLLM()
    initial = app_client.post(
        "/api/v1/chat",
        json={"message": "book it", "session_id": "booking-session"},
    )
    assert initial.status_code == 200
    assert "Reply yes to save it" in initial.json()["answer"]
    with app_client.app.state.session_factory() as session:
        assert session.query(InterviewBooking).count() == 0

    confirmed = app_client.post(
        "/api/v1/chat",
        json={"message": "yes", "session_id": "booking-session"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["booking_id"]
    with app_client.app.state.session_factory() as session:
        assert session.query(InterviewBooking).count() == 1

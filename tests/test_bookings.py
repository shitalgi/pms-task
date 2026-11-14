from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import create_database, initialize_database
from app.models.booking import InterviewBooking
from app.services.bookings import BookingService
from app.services.memory import RedisChatMemory
from tests.conftest import FakeRedis


@pytest.mark.asyncio
async def test_booking_requires_confirmation_before_persisting() -> None:
    settings = Settings(database_url="sqlite://")
    engine, factory = create_database(settings)
    initialize_database(engine)
    session: Session = factory()
    memory = RedisChatMemory(FakeRedis(), settings)
    service = BookingService(session, memory)
    parsed: dict[str, object] = {
        "intent": "booking",
        "full_name": "Avery Example",
        "email": "avery@example.com",
        "interview_date": (date.today() + timedelta(days=5)).isoformat(),
        "interview_time": "14:30",
    }

    prompt, booking_id = await service.handle("session-1", parsed, "Book an interview")
    assert "Reply yes to save it" in prompt
    assert booking_id is None
    assert session.query(InterviewBooking).count() == 0

    prompt, booking_id = await service.handle(
        "session-1",
        {"intent": "question", "confirmation": True},
        "yes",
    )
    assert "booked" in prompt.lower()
    assert booking_id
    assert session.query(InterviewBooking).count() == 1
    session.close()
    engine.dispose()


@pytest.mark.asyncio
async def test_booking_asks_for_missing_details() -> None:
    settings = Settings(database_url="sqlite://")
    engine, factory = create_database(settings)
    initialize_database(engine)
    session: Session = factory()
    service = BookingService(session, RedisChatMemory(FakeRedis(), settings))
    answer, booking_id = await service.handle(
        "session-2",
        {"intent": "booking", "full_name": "Avery Example"},
        "I want to book an interview",
    )

    assert "email address" in answer
    assert "interview date" in answer
    assert booking_id is None
    session.close()
    engine.dispose()


@pytest.mark.asyncio
async def test_booking_rejects_invalid_email_without_persisting() -> None:
    settings = Settings(database_url="sqlite://")
    engine, factory = create_database(settings)
    initialize_database(engine)
    session: Session = factory()
    memory = RedisChatMemory(FakeRedis(), settings)
    service = BookingService(session, memory)
    answer, booking_id = await service.handle(
        "session-invalid",
        {
            "intent": "booking",
            "full_name": "Avery Example",
            "email": "not-an-email",
            "interview_date": (date.today() + timedelta(days=5)).isoformat(),
            "interview_time": "14:30",
        },
        "Book me an interview",
    )

    assert "email address does not look valid" in answer
    assert booking_id is None
    assert session.query(InterviewBooking).count() == 0
    draft = await memory.get_booking_draft("session-invalid")
    assert draft == {
        "full_name": "Avery Example",
        "interview_date": (date.today() + timedelta(days=5)).isoformat(),
        "interview_time": "14:30",
    }
    session.close()
    engine.dispose()

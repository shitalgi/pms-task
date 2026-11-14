import re
from datetime import date, datetime, time
from uuid import uuid4

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.models.booking import InterviewBooking
from app.repositories.bookings import BookingRepository
from app.services.memory import RedisChatMemory

EMAIL_ADAPTER = TypeAdapter(EmailStr)
AFFIRMATIVE = re.compile(r"^\s*(yes|yeah|yep|correct|confirm|confirmed|please do|go ahead)\b", re.IGNORECASE)
NEGATIVE = re.compile(r"^\s*(no|nope|cancel|don't|do not)\b", re.IGNORECASE)


class BookingValidationError(ValueError):
    pass


class BookingService:
    _fields = ("full_name", "email", "interview_date", "interview_time")

    def __init__(self, session: Session, memory: RedisChatMemory) -> None:
        self.repository = BookingRepository(session)
        self.memory = memory

    @staticmethod
    def _validate(draft: dict[str, str]) -> dict[str, str]:
        normalized = dict(draft)
        name = normalized.get("full_name", "").strip()
        if name and (len(name) > 200 or len(name.split()) < 2):
            raise BookingValidationError("Please provide your full name (first and last name, up to 200 characters).")
        if name:
            normalized["full_name"] = name

        email = normalized.get("email", "").strip()
        if email:
            try:
                normalized["email"] = str(EMAIL_ADAPTER.validate_python(email))
            except ValidationError as exc:
                raise BookingValidationError("That email address does not look valid. Please enter it again.") from exc

        interview_date = normalized.get("interview_date", "").strip()
        if interview_date:
            try:
                parsed_date = date.fromisoformat(interview_date)
            except ValueError as exc:
                raise BookingValidationError("Please provide the interview date in YYYY-MM-DD format.") from exc
            if parsed_date <= date.today():
                raise BookingValidationError("The interview date must be in the future. Please choose another date.")
            normalized["interview_date"] = parsed_date.isoformat()

        interview_time = normalized.get("interview_time", "").strip()
        if interview_time:
            try:
                normalized["interview_time"] = time.fromisoformat(interview_time).strftime("%H:%M")
            except ValueError as exc:
                raise BookingValidationError("Please provide the interview time in 24-hour HH:MM format.") from exc
        return normalized

    @staticmethod
    def _confirmation_prompt(draft: dict[str, str]) -> str:
        return (
            "Please confirm this interview booking:\n"
            f"- Name: {draft['full_name']}\n"
            f"- Email: {draft['email']}\n"
            f"- Date: {draft['interview_date']}\n"
            f"- Time: {draft['interview_time']}\n"
            "Reply yes to save it, or no to cancel."
        )

    async def handle(
        self,
        session_id: str,
        parsed: dict[str, object],
        message: str,
    ) -> tuple[str, str | None]:
        draft = await self.memory.get_booking_draft(session_id)
        intent = str(parsed.get("intent", "question")).lower()
        if parsed.get("cancel") is True or (draft and NEGATIVE.search(message)):
            await self.memory.clear_booking_draft(session_id)
            return "The interview booking was cancelled. Let me know if you want to start again.", None
        if draft is None and intent != "booking":
            return "", None
        if draft is None:
            draft = {}

        for field in self._fields:
            value = parsed.get(field)
            if isinstance(value, str) and value.strip():
                draft[field] = value.strip()
        try:
            draft = self._validate(draft)
        except BookingValidationError as exc:
            valid_partial: dict[str, str] = {}
            for field in self._fields:
                if field not in draft:
                    continue
                try:
                    valid_partial[field] = self._validate({field: draft[field]})[field]
                except BookingValidationError:
                    continue
            await self.memory.save_booking_draft(session_id, valid_partial)
            return str(exc), None
        missing = [field for field in self._fields if not draft.get(field)]
        if missing:
            prompts = {
                "full_name": "your full name",
                "email": "your email address",
                "interview_date": "the interview date (YYYY-MM-DD)",
                "interview_time": "the interview time (24-hour HH:MM)",
            }
            await self.memory.save_booking_draft(session_id, draft)
            return "To book the interview, please provide " + ", ".join(prompts[item] for item in missing) + ".", None

        if draft.get("awaiting_confirmation") == "true":
            confirmed = parsed.get("confirmation") is True or bool(AFFIRMATIVE.match(message))
            declined = parsed.get("confirmation") is False or bool(NEGATIVE.match(message))
            if declined:
                await self.memory.clear_booking_draft(session_id)
                return "The interview booking was not saved. You can provide the details again whenever you're ready.", None
            if not confirmed:
                await self.memory.save_booking_draft(session_id, draft)
                return self._confirmation_prompt(draft), None
            booking = self.repository.create(
                InterviewBooking(
                    id=str(uuid4()),
                    full_name=draft["full_name"],
                    email=draft["email"],
                    interview_date=date.fromisoformat(draft["interview_date"]),
                    interview_time=time.fromisoformat(draft["interview_time"]),
                )
            )
            await self.memory.clear_booking_draft(session_id)
            return (
                f"Your interview is booked for {booking.interview_date.isoformat()} at "
                f"{booking.interview_time.strftime('%H:%M')}. Confirmation ID: {booking.id}.",
                booking.id,
            )

        draft["awaiting_confirmation"] = "true"
        await self.memory.save_booking_draft(session_id, draft)
        return self._confirmation_prompt(draft), None

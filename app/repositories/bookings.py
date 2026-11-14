from sqlalchemy.orm import Session

from app.models.booking import InterviewBooking


class BookingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, booking: InterviewBooking) -> InterviewBooking:
        self.session.add(booking)
        self.session.commit()
        self.session.refresh(booking)
        return booking

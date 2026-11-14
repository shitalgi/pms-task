from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, EmailStr


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str
    email: EmailStr
    interview_date: date
    interview_time: time
    created_at: datetime

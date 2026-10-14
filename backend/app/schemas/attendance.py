from pydantic import BaseModel


class CheckInResponse(BaseModel):
    success: bool
    message: str
    streakDays: int
    attendanceThisMonth: int
    checkedInAt: str

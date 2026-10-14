from typing import List
from pydantic import BaseModel


class LeaderboardEntry(BaseModel):
    rank: int
    name: str
    category: str
    score: str
    streak: int
    visitsThisMonth: int


class LeaderboardResponse(BaseModel):
    leaderboard: List[LeaderboardEntry]
    updatedAt: str

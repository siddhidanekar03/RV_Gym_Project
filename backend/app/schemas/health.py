from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class DatabaseHealth(BaseModel):
    """Database connectivity and performance metrics."""

    status: str = Field(..., description="Connection status: 'connected' | 'disconnected'")
    latency_ms: Optional[float] = Field(None, description="Round-trip query latency in milliseconds")
    dialect: Optional[str] = Field(None, description="Active database engine dialect (e.g. postgresql, sqlite)")
    error: Optional[str] = Field(None, description="Error details if connection failed")


class HealthResponse(BaseModel):
    """System health check payload."""

    status: str = Field(..., description="Overall service state: 'healthy' | 'degraded' | 'unhealthy'")
    environment: str = Field(..., description="Current operational environment")
    version: str = Field(..., description="Application version")
    timestamp: datetime = Field(..., description="Server timestamp (UTC)")
    database: DatabaseHealth = Field(..., description="Database subsystem health")

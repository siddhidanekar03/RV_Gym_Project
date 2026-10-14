from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status, Response
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.core.database import get_db, ping_database
from backend.app.core.logging import logger
from backend.app.schemas.health import HealthResponse, DatabaseHealth

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Comprehensive Health Check",
    description="Validates API availability and active database connectivity with latency measurement.",
    responses={
        200: {"description": "All subsystems healthy"},
        503: {"description": "One or more subsystems degraded or disconnected"},
    },
)
def check_health(response: Response, db: Session = Depends(get_db)) -> HealthResponse:
    now_utc = datetime.now(timezone.utc)

    try:
        db_metrics = ping_database(db)
        db_health = DatabaseHealth(
            status="connected",
            latency_ms=db_metrics["latency_ms"],
            dialect=db_metrics["dialect"],
        )
        overall_status = "healthy"
    except Exception as exc:
        logger.error(f"Health check failed database connectivity verification: {exc}")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        db_health = DatabaseHealth(
            status="disconnected",
            error="Database connection unreachable",
        )
        overall_status = "unhealthy"

    return HealthResponse(
        status=overall_status,
        environment=settings.ENVIRONMENT,
        version=settings.VERSION,
        timestamp=now_utc,
        database=db_health,
    )

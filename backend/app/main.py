import os
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.core.config import settings, validate_production_security
from backend.app.core.logging import setup_logging, logger, correlation_id_ctx
from backend.app.api.v1.api import api_router
from backend.app.api.v1.endpoints.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle management."""
    setup_logging()
    validate_production_security(settings)
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION} [{settings.ENVIRONMENT}]")
    logger.info(f"Database dialect configured: {settings.DATABASE_URL.split('://')[0]}")
    yield
    logger.info(f"Shutting down {settings.PROJECT_NAME} and releasing connection pools...")
    try:
        from backend.app.core.database import engine
        engine.dispose()
        logger.info("Database connection pool disposed cleanly.")
    except Exception as e:
        logger.error(f"Error during database engine disposal: {e}")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

# Static storage for user and administrative media uploads (backed by persistent mount)
uploads_dir = settings.get_uploads_dir()
os.makedirs(os.path.join(uploads_dir, "announcements"), exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# CORS Middleware with explicit configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Attach request correlation ID from headers or generate new UUID4."""
    corr_id = (
        request.headers.get("x-correlation-id")
        or request.headers.get("x-request-id")
        or uuid.uuid4().hex[:16]
    )
    token = correlation_id_ctx.set(corr_id)
    request.state.correlation_id = corr_id
    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = corr_id
        return response
    finally:
        correlation_id_ctx.reset(token)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Enforce defensive HTTP security headers on all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
    if settings.ENVIRONMENT in {"production", "staging"}:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    return response


# Standardized Safe Error Handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "detail": exc.detail,
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        loc = " -> ".join(str(l) for l in err.get("loc", []))
        msg = err.get("msg", "Validation error")
        errors.append(f"{loc}: {msg}")
    logger.warning(f"Validation error on {request.method} {request.url.path}: {errors}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Request validation failed",
            "details": errors,
            "status_code": 422,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.critical(f"Unhandled server error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "An unexpected internal server error occurred.",
            "status_code": 500,
        },
    )


# Mount Root Probes for Load Balancers and Container Orchestrators
app.include_router(health_router, include_in_schema=False)

# Mount API Router
app.include_router(api_router, prefix=settings.API_V1_STR)

# Static frontend distribution serving (standalone staging / production container mode)
frontend_dist_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend",
    "dist",
)
if os.path.isdir(frontend_dist_dir):
    assets_dir = os.path.join(frontend_dist_dir, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa_frontend(full_path: str):
        if full_path.startswith(("api", "uploads", "health", "ready", "docs", "redoc", "openapi")):
            raise StarletteHTTPException(status_code=404, detail="Not Found")
        target_file = os.path.join(frontend_dist_dir, full_path)
        if os.path.isfile(target_file):
            return FileResponse(target_file)
        index_file = os.path.join(frontend_dist_dir, "index.html")
        if os.path.isfile(index_file):
            return FileResponse(index_file)
        raise StarletteHTTPException(status_code=404, detail="Frontend index.html not found")


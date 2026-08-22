"""Deepfake-Resistant Provenance & Verification System - Backend Application.

Main entry point for the FastAPI platform.
"""

from contextlib import asynccontextmanager
import logging
from pathlib import Path
import time
from typing import AsyncGenerator
import uuid

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import api_v1_router
from app.api.v1.system import router as system_router
from app.config import settings
from app.database import init_db

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
)
logger = logging.getLogger("provenance.app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle manager."""
    logger.info("Initializing Provenance Platform services...")

    # Ensure upload storage directories exist
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.TEMP_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.PROCESSED_DIR).mkdir(parents=True, exist_ok=True)

    # Initialize database tables
    try:
        init_db()
        logger.info("Database schema initialized successfully")
    except Exception as e:
        logger.error("Error during database initialization: %s", e)

    logger.info("Deepfake-Resistant Provenance System is operational")
    yield
    logger.info("Shutting down Provenance Platform services...")


# Initialize FastAPI Application
app = FastAPI(
    title="Deepfake-Resistant Provenance & Verification Platform",
    description=(
        "National Government Content Provenance System. "
        "Allows official publishers to register and cryptographically sign authentic media, "
        "enabling citizens to verify content through WhatsApp and web interfaces with "
        "tamper-resistant hash chain registries."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)


# ============================================================================
# Middleware Configuration
# ============================================================================

# 1. CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time-Ms"],
)


# 2. Request ID, Performance Timing & Security Headers Middleware
@app.middleware("http")
async def security_and_timing_middleware(request: Request, call_next):
    """Inject request ID, track processing latency, and enforce security headers."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start_time = time.perf_counter()

    # Process request
    response = await call_next(request)

    # Calculate processing latency
    process_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

    # Set response headers
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = str(process_time_ms)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none';"

    # Log request summary
    logger.info(
        "%s %s -> %d (Time: %sms, ReqID: %s)",
        request.method,
        request.url.path,
        response.status_code,
        process_time_ms,
        request_id,
    )

    return response


# ============================================================================
# Exception Handlers
# ============================================================================

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Format HTTP exceptions into standard error envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "status_code": exc.status_code,
            "message": exc.detail,
            "path": request.url.path,
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Format Pydantic validation errors."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": True,
            "status_code": 422,
            "message": "Request validation failed",
            "details": exc.errors(),
            "path": request.url.path,
        },
    )


@app.exception_handler(ValueError)
async def value_error_exception_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Handle ValueErrors as Bad Request 400."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": True,
            "status_code": 400,
            "message": str(exc),
            "path": request.url.path,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Fallback handler for unhandled internal server errors."""
    logger.exception("Unhandled server exception at %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": True,
            "status_code": 500,
            "message": "An internal server error occurred.",
            "path": request.url.path,
        },
    )


# ============================================================================
# Static Files & Router Mounting
# ============================================================================

# Mount static file uploads directory
uploads_path = Path(settings.UPLOAD_DIR)
uploads_path.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")

# Top-level Health check endpoint
app.include_router(system_router)

# Mount API v1 Routes
app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)


@app.get("/", summary="Root endpoint")
def root():
    """Platform root info."""
    return {
        "title": "Deepfake-Resistant Provenance & Verification Platform",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "status": "/api/v1/status",
        "api_v1": "/api/v1",
    }

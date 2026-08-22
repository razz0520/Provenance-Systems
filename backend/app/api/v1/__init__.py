"""API v1 Router aggregation."""

from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.content import router as content_router
from app.api.v1.credentials import router as credentials_router
from app.api.v1.system import router as system_router
from app.api.v1.verify import router as verify_router
from app.api.v1.webhook import router as webhook_router

api_v1_router = APIRouter()

api_v1_router.include_router(auth_router)
api_v1_router.include_router(content_router)
api_v1_router.include_router(verify_router)
api_v1_router.include_router(credentials_router)
api_v1_router.include_router(admin_router)
api_v1_router.include_router(system_router)
api_v1_router.include_router(webhook_router)

__all__ = ["api_v1_router"]

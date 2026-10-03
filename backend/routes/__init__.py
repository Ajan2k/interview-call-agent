from fastapi import APIRouter

from .health import router as health_router
from .contacts import router as contacts_router
from .campaigns import router as campaigns_router
from .calls import router as calls_router
from .meetings import router as meetings_router
from .callbacks import router as callbacks_router
from .reports import router as reports_router
from .voice_config import router as voice_config_router
from .translate import router as translate_router
from .logs import router as logs_router
from .voice import router as voice_router
from . import voice

api_router = APIRouter(prefix="/api")

api_router.include_router(health_router)
api_router.include_router(contacts_router)
api_router.include_router(campaigns_router)
api_router.include_router(calls_router)
api_router.include_router(meetings_router)
api_router.include_router(callbacks_router)
api_router.include_router(reports_router)
api_router.include_router(voice_config_router)
api_router.include_router(translate_router)
api_router.include_router(logs_router)

__all__ = [
    "api_router",
    "voice_router",
    "voice",
    "health_router",
    "contacts_router",
    "campaigns_router",
    "calls_router",
    "meetings_router",
    "callbacks_router",
    "reports_router",
    "voice_config_router",
    "translate_router",
    "logs_router",
]

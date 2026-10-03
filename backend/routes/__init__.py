from fastapi import APIRouter

from .health import router as health_router
from .candidates import router as candidates_router
from .calls import router as calls_router
from .voice_config import router as voice_config_router
from .translate import router as translate_router
from .logs import router as logs_router
from .voice import router as voice_router
from . import voice

api_router = APIRouter(prefix="/api")

api_router.include_router(health_router)
api_router.include_router(candidates_router)
api_router.include_router(calls_router)
api_router.include_router(voice_config_router)
api_router.include_router(translate_router)
api_router.include_router(logs_router)

__all__ = [
    "api_router",
    "voice_router",
    "voice",
    "candidates_router",
    "health_router",
    "calls_router",
    "voice_config_router",
    "translate_router",
    "logs_router",
]

from contextlib import asynccontextmanager
from core.logging import setup_logging, apply_access_log_filter
LOG_FILE = setup_logging()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from routes import api_router, voice_router
import logging

import uvicorn

load_dotenv()
logging.getLogger("main").info(f"Logging to console and {LOG_FILE}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # uvicorn finishes wiring its own access-log handlers only by startup time,
    # so re-attach the polling filter here to guarantee it sticks.
    apply_access_log_filter()
    yield


app = FastAPI(
    title="TeleForce AI Call Agent API",
    description="Backend API for TeleForce AI voice calling platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voice_router)
app.include_router(api_router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

from logging_config import setup_logging, apply_access_log_filter
LOG_FILE = setup_logging()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from voice import router as voice_router
from api_routes import router as api_router
import logging

load_dotenv()
logging.getLogger("main").info(f"Logging to console and {LOG_FILE}")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voice_router)
app.include_router(api_router)


@app.on_event("startup")
def _mute_polling_access_logs():
    # uvicorn finishes wiring its own access-log handlers only by startup time,
    # so re-attach the polling filter here to guarantee it sticks.
    apply_access_log_filter()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

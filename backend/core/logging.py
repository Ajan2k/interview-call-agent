import os
import logging
import logging.handlers
from dotenv import load_dotenv

# setup_logging() runs before main.py calls load_dotenv(), so load .env here to
# make flags like LOG_API_POLLING visible at logging-setup time.
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_BASE_DIR, ".env"))

_LOG_DIR = os.path.join(_BASE_DIR, "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")
_ERROR_LOG_FILE = os.path.join(_LOG_DIR, "errors.log")
_CONVERSATION_LOG_FILE = os.path.join(_LOG_DIR, "conversation.log")

# The dashboard polls these every few seconds — their successful requests drown out
# everything useful in the console and app.log. Hidden by default; set
# LOG_API_POLLING=true in .env to see them again. Failures (non-200) always show.
_POLL_ENDPOINTS = (
    "/api/health",
    "/api/campaigns",
    "/api/logs",
    "/api/voice-config",
    "/api/contacts",
    "/api/call-history",
    "/api/meetings",
    "/api/callbacks",
)


class _PollingNoiseFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        if " 200" not in msg:
            return True  # never hide errors
        return not any(ep in msg for ep in _POLL_ENDPOINTS)


def setup_logging() -> str:
    """Send every logger (app code, uvicorn, httpx, etc.) to console plus two files:
    logs/app.log (everything, for deep debugging) and logs/errors.log (warnings/errors
    only, for a quick scan of what went wrong)."""
    os.makedirs(_LOG_DIR, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    error_handler = logging.handlers.RotatingFileHandler(
        _ERROR_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.WARNING)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(error_handler)
    root.addHandler(console_handler)

    # uvicorn attaches its own console handler to these before this runs; drop it
    # so lines aren't printed twice (they still propagate up to the root handlers above).
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []

    # uvicorn.access doesn't propagate to root, so it needs the file/error handlers directly.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.addHandler(file_handler)
    access_logger.addHandler(error_handler)

    apply_access_log_filter()

    return _LOG_FILE


def apply_access_log_filter() -> None:
    """(Re)attach the polling-noise filter to uvicorn's access logger AND all of
    its handlers. Called again at app startup because uvicorn configures its own
    logging around app import, which can leave handlers that bypass a filter
    added earlier."""
    if os.getenv("LOG_API_POLLING", "false").lower() in ("1", "true", "yes"):
        return
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _PollingNoiseFilter) for f in access_logger.filters):
        access_logger.addFilter(_PollingNoiseFilter())
    for h in access_logger.handlers:
        if not any(isinstance(f, _PollingNoiseFilter) for f in h.filters):
            h.addFilter(_PollingNoiseFilter())


def get_conversation_logger() -> logging.Logger:
    """A dedicated logger for just the human-readable call transcript
    (who said what, in what language) at logs/conversation.log — separate from the
    noisy technical app.log so a call can be reviewed at a glance."""
    logger = logging.getLogger("conversation")
    if logger.handlers:
        return logger  # already set up (e.g. module reloaded)

    os.makedirs(_LOG_DIR, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(message)s")

    handler = logging.handlers.RotatingFileHandler(
        _CONVERSATION_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # keep it out of app.log/console — this file stands alone
    return logger

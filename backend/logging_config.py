import logging
import logging.handlers
import os

_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")
_ERROR_LOG_FILE = os.path.join(_LOG_DIR, "errors.log")
_CONVERSATION_LOG_FILE = os.path.join(_LOG_DIR, "conversation.log")


def setup_logging():
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
    logging.getLogger("uvicorn.access").addHandler(file_handler)
    logging.getLogger("uvicorn.access").addHandler(error_handler)

    return _LOG_FILE


def get_conversation_logger():
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

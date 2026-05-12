import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_RESET = "\033[0m"
_DIM = "\033[2m"
_C_TS = "\033[90m"
_C_NAME = "\033[36m"
_LEVEL_COLORS = {
    "DEBUG": "\033[35m",
    "INFO": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[1;31m",
}

_STATUS_RE = re.compile(r"\bstatus=(\d{3})\b")


def _use_color() -> bool:
    log_color = (os.environ.get("LOG_COLOR") or "").lower().strip()
    if log_color in ("0", "false", "no", "off"):
        return False
    if log_color in ("1", "true", "yes", "on", "force", "always"):
        return True
    force = (os.environ.get("FORCE_COLOR") or "").lower().strip()
    if force in ("1", "true", "yes"):
        return True
    try:
        return sys.stderr.isatty()
    except (ValueError, AttributeError):
        return False


def _accent_status_codes(msg: str) -> str:
    """Highlight ``status=NNN`` for HTTP lines."""

    def repl(m: re.Match[str]) -> str:
        code = int(m.group(1))
        if code >= 500:
            c = "\033[1;31m"
        elif code >= 400:
            c = "\033[33m"
        elif code >= 300:
            c = "\033[36m"
        else:
            c = "\033[32m"
        return f"{c}status={code}{_RESET}"

    return _STATUS_RE.sub(repl, msg)


class _PlainFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
        level = f"{record.levelname:<5}"
        name = record.name
        msg = record.getMessage()
        if record.exc_info:
            msg += f" exc={self.formatException(record.exc_info).splitlines()[-1]}"
        return f"{ts} {level} {name} {msg}"


class _ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
        level_name = record.levelname
        level_color = _LEVEL_COLORS.get(level_name, "")
        level = f"{level_name:<5}"
        name = record.name
        msg = record.getMessage()
        if record.exc_info:
            msg += f" exc={self.formatException(record.exc_info).splitlines()[-1]}"
        msg = _accent_status_codes(msg)
        return (
            f"{_DIM}{_C_TS}{ts}{_RESET} "
            f"{level_color}{level}{_RESET} "
            f"{_C_NAME}{name}{_RESET} "
            f"{msg}{_RESET}"
        )


def configure_logging(*, level: LogLevel | None = None) -> None:
    """Console logging; color when stderr is a TTY or ``LOG_COLOR=1`` / ``FORCE_COLOR=1``.

    ``run-dev.sh`` pipes stderr through a shell loop (non-TTY); set ``LOG_COLOR=1`` there
    so levels and status accents stay on.
    """
    resolved = (level or os.environ.get("LOG_LEVEL") or "INFO").upper().strip()
    if resolved not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        resolved = "INFO"

    handler = logging.StreamHandler()
    handler.setFormatter(_ColorFormatter() if _use_color() else _PlainFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolved)

    # Quiet chatty libs unless explicitly debugging.
    if resolved != "DEBUG":
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("uvicorn.error").setLevel(logging.INFO)
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


@dataclass
class _Timer:
    t0: float

    def ms(self) -> int:
        return int((time.perf_counter() - self.t0) * 1000)


def timer() -> _Timer:
    return _Timer(time.perf_counter())

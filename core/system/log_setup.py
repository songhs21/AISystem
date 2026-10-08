# core/system/log_setup.py
import collections
import logging
import logging.handlers
import os
import re
import threading
import time

from config.PATH import LOG_DIR, APP_LOG, ERROR_LOG, INCIDENT_DIR
from config.version import APP_VERSION

FMT = "%(asctime)s %(levelname)-5s [%(name)s] %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"
BACKUP_DAYS = 14          # 일 단위 회전 보관 일수
INCIDENT_PRE = 50         # 오류 직전에 보관할 로그 건수
INCIDENT_POST_SEC = 10    # 오류 이후 이어 붙일 시간
INCIDENT_KEEP = 50        # 사건 파일 최대 보관 수

# 정상(<400) 응답일 때 접근 로그에서 제외할 경로 (폴링·파일 서빙)
_QUIET_PREFIXES = (
    "/api/sd/queue", "/api/sd/status", "/api/sd/jobs/active",
    "/api/system/status", "/api/system/vram", "/api/system/ollama/vram",
    "/api/system/image", "/api/system/video", "/health",
    "/api/system/client-log",
)
_TAG = "_aisystem"


def clip_text(s, n: int = 200) -> str:
    """프롬프트 등 긴 문자열을 '[길이]앞 n자' 형태로 줄인다."""
    s = s or ""
    return f"[{len(s)}]{s[:n]!r}"


class _AccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "uvicorn.access":
            return True
        try:
            _, method, path, _, status = record.args
        except Exception:
            return True
        if status < 400:
            if method == "OPTIONS":
                return False
            if path.split("?")[0].startswith(_QUIET_PREFIXES):
                return False
        return True


class IncidentHandler(logging.Handler):
    """최근 로그를 메모리에 보관하다가 ERROR 이상이 나면 앞/뒤 로그를 사건 파일로 저장."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self._buf = collections.deque(maxlen=INCIDENT_PRE)
        self._open: list[tuple[str, float]] = []   # [(파일 경로, 이어 붙일 마감 시각)]

    def emit(self, record: logging.LogRecord):
        try:
            line = self.format(record)
            now = time.time()
            self._open = [(p, u) for p, u in self._open if now <= u]
            for p, _ in self._open:
                with open(p, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            if record.levelno >= logging.ERROR and not self._open:
                self._start(record, line, now)
            self._buf.append(line)
        except Exception:
            self.handleError(record)

    def _start(self, record: logging.LogRecord, line: str, now: float):
        INCIDENT_DIR.mkdir(parents=True, exist_ok=True)
        src = re.sub(r"[^0-9A-Za-z_-]", "_", record.name)[:30]
        base = time.strftime("%Y%m%d_%H%M%S", time.localtime(now)) + f"_{src}"
        path = INCIDENT_DIR / f"{base}.log"
        n = 1
        while path.exists():
            n += 1
            path = INCIDENT_DIR / f"{base}_{n}.log"
        head = [
            f"시각: {time.strftime(DATEFMT, time.localtime(now))}",
            f"출처: {record.name}",
            f"레벨: {record.levelname}",
            f"메시지: {record.getMessage()[:500]}",
            f"버전: {APP_VERSION}",
            "=" * 60,
            f"[직전 {len(self._buf)}건]",
            *self._buf,
            "-" * 60,
            "[발생]",
            line,
            "-" * 60,
            f"[이후 {INCIDENT_POST_SEC}초]",
        ]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(head) + "\n")
        self._open.append((str(path), now + INCIDENT_POST_SEC))
        self._prune()

    def _prune(self):
        files = sorted(INCIDENT_DIR.glob("*.log"))      # 파일명이 시각순
        for old in files[:-INCIDENT_KEEP]:
            try:
                old.unlink()
            except OSError:
                pass


def _clear(logger: logging.Logger):
    for h in list(logger.handlers):
        if getattr(h, _TAG, False):
            logger.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass


def setup_logging():
    """앱 시작 시 한 번 호출. uvicorn 로깅 설정 이후에 실행되도록 startup 이벤트에서 부른다."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, os.environ.get("AISYSTEM_LOG_LEVEL", "INFO").upper(), logging.INFO)
    fmt = logging.Formatter(FMT, DATEFMT)

    app_h = logging.handlers.TimedRotatingFileHandler(
        APP_LOG, when="midnight", backupCount=BACKUP_DAYS, encoding="utf-8")
    err_h = logging.handlers.TimedRotatingFileHandler(
        ERROR_LOG, when="midnight", backupCount=BACKUP_DAYS, encoding="utf-8")
    err_h.setLevel(logging.WARNING)
    inc_h = IncidentHandler()
    con_h = logging.StreamHandler()

    for h in (app_h, err_h, inc_h, con_h):
        h.setFormatter(fmt)
        setattr(h, _TAG, True)
    app_h.addFilter(_AccessFilter())
    inc_h.addFilter(_AccessFilter())

    root = logging.getLogger()
    _clear(root)
    root.setLevel(level)
    for h in (app_h, err_h, inc_h, con_h):
        root.addHandler(h)

    # uvicorn 로거는 root로 전파되지 않으므로 파일 핸들러만 직접 붙인다 (콘솔은 uvicorn이 이미 출력)
    for name in ("uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        _clear(lg)
        for h in (app_h, err_h, inc_h):
            lg.addHandler(h)

    for name in ("urllib3", "websocket", "PIL", "httpx", "asyncio", "multipart"):
        logging.getLogger(name).setLevel(logging.WARNING)

    def _thread_hook(args):
        if args.exc_type is SystemExit:
            return
        logging.getLogger("app").error(
            "스레드 예외 thread=%s", getattr(args.thread, "name", "?"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
    threading.excepthook = _thread_hook

    logging.getLogger("app").info(
        "AISystem %s 시작 (level=%s, pid=%s)", APP_VERSION, logging.getLevelName(level), os.getpid())
# core/system/jobs.py
import threading
import time
import uuid

_jobs: dict[str, dict] = {}
_lock = threading.Lock()

JOB_TTL_SEC = 3600  # 끝난 작업을 메모리에 보관하는 시간


def create_job(kind: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _cleanup()
        _jobs[job_id] = {
            "id": job_id,
            "kind": kind,
            "status": "running",   # running | done | error
            "progress": 0.0,
            "text": "대기 중...",
            "result": None,        # done 시 {"video_path": ...}
            "error": None,
            "started_at": time.time(),
            "finished_at": None,
        }
    return job_id


def update_progress(job_id: str, value: float, text: str):
    with _lock:
        job = _jobs.get(job_id)
        if job:
            job["progress"] = value
            job["text"] = text


def finish_job(job_id: str, result: dict):
    with _lock:
        job = _jobs.get(job_id)
        if job:
            job["status"] = "done"
            job["progress"] = 1.0
            job["text"] = "완료!"
            job["result"] = result
            job["finished_at"] = time.time()


def fail_job(job_id: str, message: str):
    with _lock:
        job = _jobs.get(job_id)
        if job:
            job["status"] = "error"
            job["error"] = message
            job["finished_at"] = time.time()


def get_job(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def list_jobs(kind: str | None = None, only_active: bool = False) -> list[dict]:
    with _lock:
        _cleanup()
        jobs = [dict(j) for j in _jobs.values()]
    if kind:
        jobs = [j for j in jobs if j["kind"] == kind]
    if only_active:
        jobs = [j for j in jobs if j["status"] == "running"]
    return sorted(jobs, key=lambda j: j["started_at"], reverse=True)


def _cleanup():
    """_lock을 잡은 상태에서 호출. 오래된 완료 작업 제거."""
    now = time.time()
    expired = [
        jid for jid, j in _jobs.items()
        if j["finished_at"] and now - j["finished_at"] > JOB_TTL_SEC
    ]
    for jid in expired:
        del _jobs[jid]
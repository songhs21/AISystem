"""생성 대기열 서버 처리 (TC QU-20~27).

core/system/gen_queue.py 의 함수를 직접 부른다. 작업 스레드는 시작하지 않고(_start_worker_once 를 막음),
ComfyUI 중단 요청(_interrupt)과 PC 종료 명령(subprocess.run)은 가짜로 바꿔 호출만 기록한다.
항목은 모듈 전역 목록(_items)에 있으므로 테스트마다 새 목록과 초기 종료 상태로 바꾼다.
"""
import time

import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.system import gen_queue as q

client = TestClient(app)


@pytest.fixture
def env(monkeypatch, tmp_path):
    box = {"interrupts": 0, "cmds": [], "tmp": tmp_path}
    monkeypatch.setattr(q, "_items", [])
    monkeypatch.setattr(q, "_start_worker_once", lambda: None)
    monkeypatch.setattr(q, "_interrupt", lambda: box.__setitem__("interrupts", box["interrupts"] + 1))
    monkeypatch.setattr(q.subprocess, "run", lambda cmd, **kw: box["cmds"].append(cmd))
    for name, val in (("_shutdown_armed", False), ("_shutdown_at", None), ("_shutdown_prep", False),
                      ("_shutdown_prep_cancel", False), ("_prep_batches", 0)):
        monkeypatch.setattr(q, name, val)
    return box


def add(kind="t2i", status="waiting", cleanup=None):
    item_id = q.enqueue(kind, {"k": kind}, {"mode": kind}, cleanup)
    get(item_id)["status"] = status
    return item_id


def get(item_id):
    return next(i for i in q._items if i["id"] == item_id)


def order():
    return [i["id"] for i in q._items]


def tmp_file(env, name):
    p = env["tmp"] / name
    p.write_text("x")
    return str(p)


# QU-20 등록: 대기 상태로 맨 뒤에 추가, 조회에는 화면에 필요한 항목만 나옴 (QUD-01)
def test_qu20_enqueue_and_snapshot(env):
    a, b = add(), add("i2v")
    assert order() == [a, b] and a != b
    snap = q.snapshot()
    assert [s["id"] for s in snap] == [a, b]
    assert set(snap[0]) == {"id", "kind", "status", "progress", "text", "summary", "result", "error", "created_at"}
    assert (snap[0]["status"], snap[0]["progress"], snap[0]["text"]) == ("waiting", 0.0, "대기 중")
    assert snap[1]["kind"] == "i2v"


# QU-21 순서 변경: 대기 항목끼리만 바뀌고 실행 중·완료 위치는 유지, 목록에 없는 대기 항목은 뒤로 (QUD-02~05)
def test_qu21_reorder_waiting_only(env):
    d = add(status="done"); r = add(status="running"); a, b, c = add(), add(), add()
    q.reorder([c, b])
    assert order() == [d, r, c, b, a]


def test_qu21_reorder_ignores_unknown_duplicate_and_non_waiting(env):
    d = add(status="done"); r = add(status="running"); a, b, c = add(), add(), add()
    q.reorder(["nope", b, b, r, d, a])
    assert order() == [d, r, b, a, c]


# QU-22 항목 제거: 대기=제거+임시파일 삭제, 실행 중=중단 요청(항목 유지·종료 예약 해제), 완료·실패=목록에서 제거, 없는 id=not_found (QUD-06~09)
def test_qu22_remove_waiting_deletes_temp_files(env):
    f = tmp_file(env, "mask.png")
    a = add(cleanup=[f])
    assert q.remove(a) == "removed"
    assert order() == [] and not (env["tmp"] / "mask.png").exists()
    assert env["interrupts"] == 0


def test_qu22_remove_running_requests_cancel(env, monkeypatch):
    r = add(status="running")
    monkeypatch.setattr(q, "_shutdown_armed", True)
    assert q.remove(r) == "cancelling"
    assert order() == [r] and q.snapshot()[0]["status"] == "cancelling"
    assert env["interrupts"] == 1 and q.shutdown_state()["armed"] is False


@pytest.mark.parametrize("status", ["done", "error"])
def test_qu22_remove_finished(env, status):
    x = add(status=status)
    assert q.remove(x) == "removed" and order() == [] and env["interrupts"] == 0


def test_qu22_remove_unknown(env):
    add()
    assert q.remove("nope") == "not_found" and len(order()) == 1 and env["interrupts"] == 0


# QU-23 전체 취소: 대기 전부 제거(임시파일 삭제) + 실행 중 중단 요청, 완료는 유지, 반환값=제거 수+실행 중 1, 종료 예약 해제 (QUD-10~12)
def test_qu23_clear_pending(env, monkeypatch):
    f = tmp_file(env, "m.png")
    d = add(status="done"); r = add(status="running"); add(cleanup=[f]); add()
    monkeypatch.setattr(q, "_shutdown_armed", True)
    monkeypatch.setattr(q, "_shutdown_prep", True)
    assert q.clear_pending() == 3
    assert order() == [d, r] and not (env["tmp"] / "m.png").exists()
    assert q.snapshot()[1]["status"] == "cancelling" and env["interrupts"] == 1
    assert q.shutdown_state()["armed"] is False and q._shutdown_prep_cancel is True


def test_qu23_clear_without_running(env):
    add(); add()
    assert q.clear_pending() == 2 and order() == [] and env["interrupts"] == 0
    assert q.clear_pending() == 0


# QU-24 완료·실패 항목은 최근 10개만 유지, 대기·실행 중은 영향 없음 (QUD-13)
def test_qu24_finished_trimmed_to_max(env):
    waiting = add()
    ids = []
    for _ in range(12):
        i = add(status="running")
        q._finish(get(i), "done", result={})
        ids.append(i)
    assert q.MAX_FINISHED == 10
    kept = order()
    assert kept[0] == waiting and kept[1:] == ids[2:]


# QU-25 작업 실행: 진행률 반영·완료 결과, 실패 메시지, 완료 이벤트 없음, 알 수 없는 종류, 취소 (QUD-14~18)
def run_with(monkeypatch, runner, cancel=False):
    monkeypatch.setitem(q._runners, "t2i", runner)
    i = add(status="running")
    item = get(i)
    item["cancel"] = cancel
    q._run_item(item)
    return item


def test_qu25_done_with_progress(env, monkeypatch):
    seen = {}

    def runner(payload):
        yield {"type": "progress", "value": 0.5, "text": "절반"}
        seen["mid"] = (item_ref[0]["progress"], item_ref[0]["text"])
        yield {"type": "done", "image_path": "a.png", "gen_id": 3}

    item_ref = []
    monkeypatch.setitem(q._runners, "t2i", runner)
    i = add(status="running"); item_ref.append(get(i))
    q._run_item(item_ref[0])
    item = item_ref[0]
    assert seen["mid"] == (0.5, "절반")
    assert (item["status"], item["progress"], item["text"]) == ("done", 1.0, "완료!")
    assert item["result"] == {"image_path": "a.png", "gen_id": 3}


def test_qu25_runner_exception_becomes_error(env, monkeypatch):
    def runner(payload):
        yield {"type": "progress", "value": 0.1, "text": "x"}
        raise RuntimeError("boom")

    item = run_with(monkeypatch, runner)
    assert (item["status"], item["error"], item["text"]) == ("error", "boom", "실패")


def test_qu25_no_done_event_is_error(env, monkeypatch):
    item = run_with(monkeypatch, lambda p: iter([{"type": "progress", "value": 0.2, "text": "x"}]))
    assert item["status"] == "error" and item["error"] == "결과를 받지 못함"


def test_qu25_unknown_kind_is_error(env, monkeypatch):
    monkeypatch.delitem(q._runners, "zzz", raising=False)
    i = add(kind="zzz", status="running")
    item = get(i)
    q._run_item(item)
    assert item["status"] == "error" and "알 수 없는 작업 종류: zzz" in item["error"]


def test_qu25_cancel_removes_item_and_interrupts(env, monkeypatch):
    item = run_with(monkeypatch, lambda p: iter([{"type": "progress", "value": 0.1, "text": "x"}]), cancel=True)
    assert item not in q._items and env["interrupts"] == 1


def test_qu25_error_after_cancel_is_treated_as_cancel(env, monkeypatch):
    def runner(payload):
        item_ref["i"]["cancel"] = True
        raise RuntimeError("interrupted")
        yield

    item_ref = {}
    monkeypatch.setitem(q._runners, "t2i", runner)
    i = add(status="running"); item_ref["i"] = get(i)
    q._run_item(item_ref["i"])
    assert item_ref["i"] not in q._items


# QU-26 PC 종료 예약: 켜기·끄기, 종료 예약 중 남은 초와 취소, 큐가 비면 종료 절차 시작 (QUD-19~22)
def test_qu26_shutdown_toggle_state(env):
    q.set_shutdown(True)
    assert q.shutdown_state() == {"armed": True, "remaining": 0, "extracting": False,
                                  "batches": 0, "max_batches": q.SHUTDOWN_MAX_BATCHES}
    q.set_shutdown(False)
    assert q.shutdown_state()["armed"] is False


def test_qu26_abort_when_nothing_scheduled(env):
    q.set_shutdown(True)
    assert q.abort_shutdown() is False
    assert q.shutdown_state()["armed"] is False and env["cmds"] == []


def test_qu26_abort_scheduled_shutdown(env, monkeypatch):
    monkeypatch.setattr(q, "_shutdown_at", time.time() - 10)
    assert 48 <= q.shutdown_state()["remaining"] <= 50
    assert q.abort_shutdown() is True
    assert env["cmds"] == [["shutdown", "/a"]] and q.shutdown_state()["remaining"] == 0


class FakeThread:
    started = []

    def __init__(self, target=None, daemon=None):
        self.target = target

    def start(self):
        FakeThread.started.append(self.target)


def test_qu26_maybe_shutdown_starts_only_when_queue_empty(env, monkeypatch):
    FakeThread.started = []
    monkeypatch.setattr(q.threading, "Thread", FakeThread)
    add(status="done")
    w = add()
    q.set_shutdown(True)
    q._maybe_shutdown()
    assert FakeThread.started == [] and q.shutdown_state()["armed"] is True
    q.remove(w)
    q._maybe_shutdown()
    assert FakeThread.started == [q._shutdown_sequence]
    assert q.shutdown_state()["armed"] is False and q.shutdown_state()["extracting"] is True


# QU-27 API 경로가 위 함수에 연결됨 (QUD-23)
def test_qu27_routes(env):
    a, b = add(), add()
    body = client.get("/api/sd/queue").json()
    assert [i["id"] for i in body["items"]] == [a, b] and body["shutdown"]["armed"] is False
    assert client.post("/api/sd/queue/reorder", json={"ids": [b, a]}).json()["items"][0]["id"] == b
    assert client.post("/api/sd/queue/shutdown", json={"enabled": True}).json()["armed"] is True
    assert client.post("/api/sd/queue/shutdown/abort").json() == {"aborted": False}
    assert client.delete(f"/api/sd/queue/{a}").json() == {"result": "removed"}
    assert client.delete("/api/sd/queue/nope").json() == {"result": "not_found"}
    assert client.delete("/api/sd/queue").json() == {"cancelled": 1}

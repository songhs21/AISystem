"""GN-10 관찰: 요청 본문이 일부만 전달된 채 연결이 끊기면 서버가 어떻게 동작하는지 본다.
실행: python tests/api/observe_partial_body.py   (백엔드 8000 기동 필요)
본문을 끝까지 보내지 않으므로 실제 생성은 시작되지 않는다. 결과와 uvicorn 콘솔 로그를 함께 확인한다.
"""
import json
import socket
import time

import requests

HOST, PORT = "127.0.0.1", 8000


def queue_len():
    return len(requests.get(f"http://{HOST}:{PORT}/api/sd/queue", timeout=5).json()["items"])


def send_partial(body: bytes, declared_length: int):
    s = socket.create_connection((HOST, PORT), timeout=5)
    head = (f"POST /api/sd/queue/t2i HTTP/1.1\r\nHost: {HOST}:{PORT}\r\n"
            f"Content-Type: application/json\r\nContent-Length: {declared_length}\r\n"
            f"Connection: close\r\n\r\n").encode()
    s.sendall(head + body)
    time.sleep(0.5)
    try:
        s.settimeout(1)
        reply = s.recv(4096)
    except OSError:
        reply = b""
    s.close()
    return reply


full = json.dumps({"checkpoint": "dummy.safetensors", "prompt": "1girl"}).encode()
for label, part in (("본문 절반", full[: len(full) // 2]), ("본문 0바이트", b"")):
    before = queue_len()
    reply = send_partial(part, len(full))
    time.sleep(1.5)
    after = queue_len()
    print(f"[{label}] 서버 응답={reply[:80]!r} 큐 {before} → {after}")
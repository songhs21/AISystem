# api/main.py
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from config.version import APP_VERSION
from core.db import init_db
from core.llm_db import init_llm_db
from core.llm import memory_worker
from core.system import comfy_idle
from core.system.log_setup import setup_logging
from api.routers import sd, history, inpaint, system
from api.routers import llm as llm_router

app = FastAPI(title="AISystem", version=APP_VERSION)

# CORS (React 개발 서버 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# 422 응답에서 input/ctx 제외 — NaN/inf 값이 본문에 실리면 JSON 직렬화 실패로 500이 됨 (PLAN Q-16)
@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    errors = [{"type": e["type"], "loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


# 라우터 등록
app.include_router(sd.router)
app.include_router(history.router)
app.include_router(inpaint.router)
app.include_router(system.router)
app.include_router(llm_router.router)

# 정적 파일 (React 빌드 결과물)
# app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")


@app.on_event("startup")
def startup():
    setup_logging()      # uvicorn 로깅 설정 이후에 실행되어야 하므로 startup에서 호출
    init_db()
    init_llm_db()
    comfy_idle.start()
    memory_worker.start()


@app.get("/health")
def health():
    return {"status": "ok"}
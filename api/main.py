# api/main.py
import sys
import logging
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from core.db import init_db
from api.routers import sd, history, inpaint, system

app = FastAPI(title="AISystem")

# CORS (React 개발 서버 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(sd.router)
app.include_router(history.router)
app.include_router(inpaint.router)
app.include_router(system.router)

# 정적 파일 (React 빌드 결과물)
# app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")


@app.on_event("startup")
def startup():
    init_db()
    logging.info("AISystem API 시작")


@app.get("/health")
def health():
    return {"status": "ok"}

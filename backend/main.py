from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from facility_db import init_db
from facility_api import router

app = FastAPI(
    title="نظام إدارة وتشغيل المنشآت API",
    description="MVP متعدد المنشآت لإدارة المنشآت الصغيرة والمتوسطة",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def root():
    return {"name": "نظام إدارة وتشغيل المنشآت", "version": app.version, "ok": True}


@app.get("/health")
def health():
    return {"ok": True, "service": "facility-management", "database": "sqlite"}


app.include_router(router, prefix="/api")

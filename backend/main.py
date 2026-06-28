import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes_chat import router as chat_router
from fast_core.logging_config import setup_logging
from api.routes_session import router as session_router
from persistence import init_db

setup_logging()
init_db()

app = FastAPI(title="Business Agent swarm society backend")

default_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
allowed_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_CORS_ORIGINS", ",".join(default_origins)).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(chat_router, prefix="/api")
app.include_router(session_router, prefix="/api")

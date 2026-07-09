import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
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
deployment_origins = [
    os.getenv("FRONTEND_URL"),
    os.getenv("VERCEL_FRONTEND_URL"),
]
allowed_origins = [
    origin.strip()
    for origin in (
        os.getenv("FRONTEND_CORS_ORIGINS", ",".join(default_origins)).split(",")
        + [origin for origin in deployment_origins if origin]
    )
    if origin.strip()
]
allowed_origin_set = set(allowed_origins)


@app.middleware("http")
async def reject_untrusted_cookie_origin(request, call_next):
    origin = request.headers.get("origin")
    if (
        origin
        and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and origin not in allowed_origin_set
        and "*" not in allowed_origin_set
    ):
        return JSONResponse(
            status_code=403,
            content={
                "detail": {
                    "code": "ORIGIN_NOT_ALLOWED",
                    "message": "Request origin is not allowed",
                }
            },
        )
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Last-Event-ID"],
)

app.include_router(chat_router, prefix="/api")
app.include_router(session_router, prefix="/api")

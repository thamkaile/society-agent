"""Start the local Genesis FastAPI backend with vendored dependency bootstrap."""

from __future__ import annotations

import os

from runtime_bootstrap import bootstrap_runtime, ensure_compatible_python

ensure_compatible_python()
bootstrap_runtime()

import uvicorn


def main() -> None:
    host = os.getenv("GENESIS_BACKEND_HOST", "127.0.0.1")
    port = int(os.getenv("GENESIS_BACKEND_PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()

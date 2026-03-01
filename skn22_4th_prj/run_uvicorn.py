import os

import uvicorn


def _as_bool(value: str, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "skn22_4th_prj.settings")

    host = os.getenv("UVICORN_HOST", "0.0.0.0")
    port = int(os.getenv("UVICORN_PORT", "8000"))
    reload_enabled = _as_bool(os.getenv("UVICORN_RELOAD"), default=True)

    uvicorn.run(
        "skn22_4th_prj.asgi:application",
        host=host,
        port=port,
        reload=reload_enabled,
    )

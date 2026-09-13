from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent
BASE_DIR = APP_DIR.parent
ROOT_DIR = BASE_DIR.parent.parent

load_dotenv(ROOT_DIR / ".env")
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("JOYOPC_DATABASE_URL", f"sqlite:///{BASE_DIR / 'joyopc.db'}")
WEB_DIR = Path(os.getenv("JOYOPC_WEB_DIR", str(BASE_DIR.parent / "web"))).resolve()
STORAGE_DIR = Path(os.getenv("JOYOPC_STORAGE_DIR", str(BASE_DIR / "storage"))).resolve()
UPLOAD_DIR = STORAGE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_MB = int(os.getenv("JOYOPC_MAX_UPLOAD_MB", "25"))

SALEOR_GRAPHQL_URL = os.getenv("SALEOR_GRAPHQL_URL", "").rstrip("/")
SALEOR_APP_TOKEN = os.getenv("SALEOR_APP_TOKEN", "")
SALEOR_MCP_URL = os.getenv("SALEOR_MCP_URL", "").rstrip("/")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
JOYOPC_TEXT_MODEL = os.getenv("JOYOPC_TEXT_MODEL", "gpt-4.1-mini")


def upsert_dotenv(updates: dict[str, str], *, path: Path | None = None) -> Path:
    """Write non-secret identifiers and secrets to the local gitignored .env only."""
    target = path or (ROOT_DIR / ".env")
    lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
        os.environ[key] = value
    target.write_text("\n".join(out) + "\n", encoding="utf-8")
    return target

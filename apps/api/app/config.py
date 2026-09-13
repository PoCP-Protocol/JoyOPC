from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv("JOYOPC_DATABASE_URL", f"sqlite:///{BASE_DIR / 'joyopc.db'}")
WEB_DIR = Path(os.getenv("JOYOPC_WEB_DIR", str(BASE_DIR.parent / "web"))).resolve()
STORAGE_DIR = Path(os.getenv("JOYOPC_STORAGE_DIR", str(BASE_DIR / "storage"))).resolve()
UPLOAD_DIR = STORAGE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_MB = int(os.getenv("JOYOPC_MAX_UPLOAD_MB", "25"))

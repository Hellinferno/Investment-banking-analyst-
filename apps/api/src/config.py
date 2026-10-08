"""Load the same environment and data paths for CLI, API and Docker entry points."""
import os
from pathlib import Path

from dotenv import load_dotenv

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent.parent
for candidate in (API_ROOT / ".env", REPO_ROOT / ".env"):
    load_dotenv(candidate, override=False)

DATA_ROOT = Path(os.getenv("AIBAA_DATA_DIR", str(API_ROOT.parent / "data"))).resolve()
OUTPUT_ROOT = DATA_ROOT / "outputs"
UPLOAD_ROOT = DATA_ROOT / "uploads"

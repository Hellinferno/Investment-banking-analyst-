import os

from fastapi import APIRouter, HTTPException

from dependencies import CurrentUserDep
from tools.research_evidence import research_mode
from tools.serpapi_client import SearchError

router = APIRouter(prefix="/research", tags=["Research"])


@router.get("/status")
def research_status(current_user: CurrentUserDep):
    try:
        mode = research_mode()
    except SearchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return {"mode": mode, "search_configured": bool(os.getenv("SERPAPI_API_KEY", "").strip()),
            "synthesis_configured": bool(os.getenv("GEMINI_API_KEY") or os.getenv("NVIDIA_API_KEY")),
            "queries_per_run": 4, "max_http_attempts_per_run": 8, "cache_ttl_minutes": 30}

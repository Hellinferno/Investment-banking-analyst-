import sys
import os
from pathlib import Path

# Add the src directory to Python path for proper imports
src_path = Path(__file__).parent
sys.path.insert(0, str(src_path))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings

from routers import deals, documents, agents, outputs

class Settings(BaseSettings):
    app_name: str = "AIBAA Orchestration API"
    version: str = "1.0.0"

settings = Settings()
app = FastAPI(title=settings.app_name, version=settings.version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(deals.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")
app.include_router(outputs.deal_router, prefix="/api/v1")
app.include_router(outputs.output_router, prefix="/api/v1")

@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok"}

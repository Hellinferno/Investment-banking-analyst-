"""
ARQ worker entry point for background tasks.

Run with: python -m src.worker
Or:        arq apps.api.src.worker.Settings
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from arq import func
from arq.connections import RedisSettings

# Ensure src/ is on path
_src = str(Path(__file__).parent.parent)
if _src not in sys.path:
    sys.path.insert(0, _src)

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


# ---------------------------------------------------------------------------
# Task functions — registered with arq.func() for ARQ 0.27
# ---------------------------------------------------------------------------

async def run_agent_task(ctx: dict[str, Any], deal_id: str, run_id: str) -> dict[str, Any]:
    """
    ARQ job: execute an agent run in the background.
    Publishes events to Redis pub/sub for SSE clients.
    """
    redis = ctx["redis"]

    async def _publish(event: str, data: dict[str, Any]) -> None:
        payload = json.dumps({"event": event, "run_id": run_id, "data": data})
        try:
            await redis.publish(f"run:{run_id}", payload)
        except Exception as exc:
            logger.warning("Redis publish failed: %s", exc)

    db = None
    try:
        from database import SessionLocal
        from store import store
        from persistence import persist_run_bundle

        db = SessionLocal()
        run = store.agent_runs.get(run_id)
        if not run:
            logger.error("run_not_found", run_id=run_id)
            return {"ok": False, "error": "Run not found in store"}

        run.status = "running"
        await _publish("run.started", {"status": "running"})

        from agents.modeling import FinancialModelingAgent
        from agents.lbo_modeling import LBOModelingAgent
        from agents.pitchbook import PitchbookAgent
        from agents.due_diligence import DueDiligenceAgent
        from agents.research import ResearchAgent
        from agents.doc_drafter import DocDrafterAgent
        from agents.coordination import CoordinationAgent

        dispatch: dict[str, type] = {
            "modeling": FinancialModelingAgent,
            "lbo_modeling": LBOModelingAgent,
            "pitchbook": PitchbookAgent,
            "due_diligence": DueDiligenceAgent,
            "research": ResearchAgent,
            "doc_drafter": DocDrafterAgent,
            "coordination": CoordinationAgent,
        }

        agent_type = run.agent_type
        agent_cls = dispatch.get(agent_type)
        if agent_cls is None:
            run.status = "failed"
            run.error_message = f"Unknown agent type: {agent_type}"
            await _publish("run.failed", {"error": run.error_message})
            persist_run_bundle(db, run_id)
            return {"ok": False, "error": run.error_message}

        agent = agent_cls(deal_id=deal_id, input_payload=run.input_payload)
        agent.run_id = run_id
        await _publish("run.agent_initialized", {"agent_type": agent_type})

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: agent.run())

        run.status = "completed"
        run.confidence_score = getattr(agent, "confidence_score", None)
        await _publish("run.completed", {"status": "completed", "confidence": run.confidence_score})
        persist_run_bundle(db, run_id)

        logger.info("agent_task_completed", run_id=run_id)
        return {"ok": True, "run_id": run_id, "status": "completed"}

    except Exception as exc:
        logger.exception("run_agent_task_failed", run_id=run_id)
        try:
            run = store.agent_runs.get(run_id)
            if run:
                run.status = "failed"
                run.error_message = str(exc)
                if db:
                    await _publish("run.failed", {"error": str(exc)})
                    persist_run_bundle(db, run_id)
        except Exception:
            pass
        return {"ok": False, "error": str(exc)}

    finally:
        if db:
            db.close()


async def run_rag_indexing(ctx: dict[str, Any], doc_id: str, deal_id: str) -> dict[str, Any]:
    """ARQ job: chunk, embed, and index a parsed document in ChromaDB."""
    redis = ctx["redis"]

    async def _publish(event: str, data: dict[str, Any]) -> None:
        try:
            payload = json.dumps({"event": event, "doc_id": doc_id, "data": data})
            await redis.publish(f"doc:{doc_id}", payload)
        except Exception as exc:
            logger.warning("Redis publish failed: %s", exc)

    try:
        await _publish("rag.indexing_started", {"status": "indexing"})
        from database import SessionLocal
        from db_models import DocumentModel
        from rag import index_document
        from store import store

        db = SessionLocal()
        try:
            doc = db.query(DocumentModel).filter(DocumentModel.id == doc_id).first()
            if not doc or not doc.parsed_text:
                await _publish("rag.indexing_failed", {"error": "Document not found or not parsed"})
                return {"ok": False, "error": "Document not found or not parsed"}

            index_document(doc_id=doc.id, deal_id=doc.deal_id, text=doc.parsed_text, source_filename=doc.filename)
            doc.rag_status = "indexed"
            db.commit()

            doc_record = store.documents.get(doc_id)
            if doc_record:
                doc_record.rag_status = "indexed"

            await _publish("rag.indexing_completed", {"status": "indexed"})
            logger.info("rag_indexing_completed", doc_id=doc_id)
            return {"ok": True, "doc_id": doc_id, "status": "indexed"}
        finally:
            db.close()

    except Exception as exc:
        logging.getLogger(__name__).exception("run_rag_indexing_failed", doc_id=doc_id)
        await _publish("rag.indexing_failed", {"error": str(exc)})
        return {"ok": False, "error": str(exc)}


async def dispatch_webhook_event(
    ctx: dict[str, Any],
    webhook_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """ARQ job: deliver a webhook event asynchronously."""
    from database import SessionLocal
    from db_models import WebhookModel
    from routers.webhooks import deliver_webhook

    db = SessionLocal()
    try:
        hook = db.query(WebhookModel).filter(WebhookModel.id == webhook_id).first()
        if not hook:
            return {"ok": False, "error": "Webhook not found"}
        success, error = await deliver_webhook(hook, event_type, payload)
        return {"ok": success, "error": error}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# ARQ Settings — registers task functions via arq.func()
# ---------------------------------------------------------------------------

class Settings:
    redis_settings = RedisSettings(host="localhost", port=6379, database=0)
    job_timeout = 300
    max_jobs = 100
    keep_result = 3600
    keep_job_logs = 3600

    functions = [
        func(run_agent_task),
        func(run_rag_indexing),
        func(dispatch_webhook_event),
    ]


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import logging as _logging
    import asyncio as _asyncio

    _logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [arq] %(message)s",
    )
    print(f"Starting ARQ worker... (Redis: {REDIS_URL})")

    # Python 3.14 requires an explicit event loop in the main thread
    _loop = _asyncio.new_event_loop()
    _asyncio.set_event_loop(_loop)

    from arq import run_worker
    run_worker(Settings)

"""
Pydantic models for the TinyFish Web Agent API.

TinyFish uses SSE streaming: the client POSTs a URL + goal, then receives
a stream of events (STARTED -> PROGRESS -> COMPLETE). These models capture
the request payload, individual SSE events, and the final result wrapper.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class WebAgentRequest(BaseModel):
    """Payload sent to the TinyFish Web Agent endpoint."""

    url: str
    goal: str
    browser_profile: Literal["lite", "stealth"] = "lite"


class SSEEvent(BaseModel):
    """
    A single Server-Sent Event from the TinyFish stream.

    Event types:
      - STARTED:   run acknowledged, contains runId
      - PROGRESS:  intermediate step (has purpose text)
      - HEARTBEAT: keep-alive
      - COMPLETE:  final event, status is COMPLETED or FAILED
    """

    type: str
    run_id: str = Field(default="", alias="runId")
    timestamp: str = ""
    purpose: str = ""
    status: str = ""
    result_json: Any = Field(default=None, alias="resultJson")
    error: str | None = None

    model_config = {"populate_by_name": True}


class WebAgentResult(BaseModel):
    """Normalised result returned to callers after the SSE stream completes."""

    success: bool
    data: dict | list | None = None
    error: str | None = None
    run_id: str = ""
    elapsed_seconds: float = 0.0

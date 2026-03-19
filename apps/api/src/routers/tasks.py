"""Tasks router — CRUD for TaskModel (AI-generated + manual tasks)."""
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional

from db_models import TaskModel
from dependencies import get_current_user, get_db
from models import APIResponse, Meta, PriorityStr
from persistence import get_deal_for_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/deals", tags=["Tasks"])


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    priority: PriorityStr = "medium"
    owner: str = Field(default="", max_length=100)


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    status: Optional[str] = Field(default=None)
    priority: Optional[PriorityStr] = None
    owner: Optional[str] = Field(default=None, max_length=100)


def _serialize_task(t: TaskModel) -> dict:
    return {
        "task_id": t.id,
        "deal_id": t.deal_id,
        "title": t.title,
        "status": t.status,
        "priority": t.priority,
        "owner": t.owner,
        "is_ai_generated": t.is_ai_generated,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


@router.get("/{deal_id}/tasks", response_model=APIResponse)
async def list_tasks(
    deal_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    deal = get_deal_for_user(db, deal_id, current_user["tenant_id"])
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    tasks = (
        db.query(TaskModel)
        .filter(TaskModel.deal_id == deal_id)
        .order_by(TaskModel.created_at.desc())
        .all()
    )
    return APIResponse(
        success=True,
        data={"tasks": [_serialize_task(t) for t in tasks], "total": len(tasks)},
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.post("/{deal_id}/tasks", response_model=APIResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    deal_id: str,
    payload: TaskCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    deal = get_deal_for_user(db, deal_id, current_user["tenant_id"])
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    task = TaskModel(
        id=str(uuid.uuid4()),
        deal_id=deal_id,
        title=payload.title,
        priority=payload.priority,
        owner=payload.owner,
        is_ai_generated=False,
        status="todo",
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    return APIResponse(
        success=True,
        data=_serialize_task(task),
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.patch("/{deal_id}/tasks/{task_id}", response_model=APIResponse)
async def update_task(
    deal_id: str,
    task_id: str,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    deal = get_deal_for_user(db, deal_id, current_user["tenant_id"])
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    task = db.query(TaskModel).filter(TaskModel.id == task_id, TaskModel.deal_id == deal_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    valid_statuses = {"todo", "in_progress", "done", "blocked"}
    if payload.title is not None:
        task.title = payload.title
    if payload.status is not None:
        if payload.status not in valid_statuses:
            raise HTTPException(status_code=422, detail=f"status must be one of {valid_statuses}")
        task.status = payload.status
    if payload.priority is not None:
        task.priority = payload.priority
    if payload.owner is not None:
        task.owner = payload.owner

    db.commit()
    db.refresh(task)

    return APIResponse(
        success=True,
        data=_serialize_task(task),
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.delete("/{deal_id}/tasks/{task_id}", response_model=APIResponse)
async def delete_task(
    deal_id: str,
    task_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    deal = get_deal_for_user(db, deal_id, current_user["tenant_id"])
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    task = db.query(TaskModel).filter(TaskModel.id == task_id, TaskModel.deal_id == deal_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    db.delete(task)
    db.commit()

    return APIResponse(
        success=True,
        data={"deleted": task_id},
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )

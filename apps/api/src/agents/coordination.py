"""
CoordinationAgent — extracts tasks, decisions, and follow-ups from meeting notes.

Outputs:
  1. TaskModel records persisted to the database
  2. Markdown meeting summary file (.md)
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from agents.base import BaseAgent
from agents.prompt_builder import PromptBuilder
from engine.llm import ask_llm

logger = logging.getLogger(__name__)

_OUTPUT_DIR = str(Path(__file__).resolve().parent.parent.parent.parent / "data" / "outputs")


class CoordinationAgent(BaseAgent):
    def __init__(self, deal_id: str, input_payload: dict):
        super().__init__(
            agent_type="coordination",
            task_name="extract_tasks",
            deal_id=deal_id,
            input_payload=input_payload,
        )
        self.system_prompt = PromptBuilder.get_system_prompt("coordination")

    def run(self) -> str:
        try:
            self.think("Loading all deal documents for task extraction and coordination.")
            doc_context = self._extract_document_context()
            deal_info = self._get_deal_info()
            deal_name = deal_info.get("deal_name", "Deal")

            if not doc_context.strip():
                self.think("No parsed documents found — skipping task extraction.")
                self.complete(confidence=0.30)
                return self.run_id

            self.act("ask_llm", "extracting tasks and action items via LLM")
            prompt = PromptBuilder.build_coordination_prompt(doc_context)
            raw = ask_llm(self.system_prompt, prompt)
            self.observe(f"LLM response received ({len(raw)} chars). Parsing tasks.")

            tasks_data = self._parse_tasks_data(raw)

            # Persist tasks to DB
            task_count = self._create_tasks_in_db(tasks_data.get("tasks", []))
            self.observe(f"Created {task_count} tasks in database.")

            # Write markdown summary
            os.makedirs(_OUTPUT_DIR, exist_ok=True)
            date_str = datetime.now().strftime("%Y%m%d")
            safe_name = re.sub(r"[^\w\-]", "_", deal_name)
            md_filename = f"{safe_name}_MeetingSummary_{date_str}.md"
            md_path = os.path.join(_OUTPUT_DIR, md_filename)

            self._write_markdown_summary(md_path, deal_info, tasks_data)
            self._register_output(md_path, output_type="markdown", output_category="coordination")
            self.observe(f"Meeting summary written: {md_filename}")

            self.complete(confidence=0.85)

        except Exception as exc:
            logger.exception("CoordinationAgent failed for deal %s", self.deal_id)
            self.fail(str(exc))

        return self.run_id

    def _parse_tasks_data(self, raw: str) -> dict:
        match = re.search(r"\{[\s\S]*\}", raw.strip())
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        logger.warning("CoordinationAgent: could not parse LLM JSON, using fallback.")
        return {
            "meeting_summary": raw[:500],
            "tasks": [],
            "decisions": [],
            "open_questions": [],
            "next_steps": [],
        }

    def _create_tasks_in_db(self, tasks: list) -> int:
        """Persist extracted tasks as TaskModel records."""
        if not tasks:
            return 0

        from database import SessionLocal, ensure_database_ready
        from db_models import TaskModel
        import uuid as uuid_mod

        ensure_database_ready()
        created = 0
        with SessionLocal() as db:
            for task_item in tasks:
                if not isinstance(task_item, dict):
                    continue
                title = task_item.get("title", "").strip()
                if not title:
                    continue
                # Append due_date and description to owner field (TaskModel has limited columns)
                owner_parts = [task_item.get("owner", "Agent")]
                due = task_item.get("due_date", "")
                if due and due != "TBD":
                    owner_parts.append(f"Due: {due}")
                task_record = TaskModel(
                    id=str(uuid_mod.uuid4()),
                    deal_id=self.deal_id,
                    title=title,
                    priority=task_item.get("priority", "medium"),
                    owner=" | ".join(filter(None, owner_parts)),
                    is_ai_generated=True,
                    status="todo",
                )
                db.add(task_record)
                created += 1
            db.commit()

        return created

    def _write_markdown_summary(self, md_path: str, deal_info: dict, tasks_data: dict) -> None:
        deal_name = deal_info.get("deal_name", "Deal")
        company = deal_info.get("company_name", "Company")
        now = datetime.now().strftime("%B %d, %Y")

        lines = [
            f"# Meeting Summary — {deal_name}",
            f"**Company:** {company}  ",
            f"**Date:** {now}  ",
            "",
            "---",
            "",
            "## Summary",
            "",
            tasks_data.get("meeting_summary", ""),
            "",
        ]

        tasks = tasks_data.get("tasks", [])
        if tasks:
            lines += ["## Action Items", ""]
            for i, task in enumerate(tasks, start=1):
                if isinstance(task, dict):
                    priority = task.get("priority", "medium").upper()
                    owner = task.get("owner", "TBD")
                    due = task.get("due_date", "TBD")
                    lines.append(f"**{i}. {task.get('title', '')}**  ")
                    lines.append(f"Priority: `{priority}` | Owner: {owner} | Due: {due}  ")
                    desc = task.get("description", "")
                    if desc:
                        lines.append(f"_{desc}_  ")
                    lines.append("")

        decisions = tasks_data.get("decisions", [])
        if decisions:
            lines += ["## Key Decisions", ""]
            for dec in decisions:
                if isinstance(dec, dict):
                    lines.append(f"- **{dec.get('decision', '')}** ({dec.get('decided_by', '')})")
                    rationale = dec.get("rationale", "")
                    if rationale:
                        lines.append(f"  _{rationale}_")
            lines.append("")

        questions = tasks_data.get("open_questions", [])
        if questions:
            lines += ["## Open Questions", ""]
            for q in questions:
                if isinstance(q, dict):
                    lines.append(f"- {q.get('question', '')} _(Owner: {q.get('owner', 'TBD')})_")
            lines.append("")

        next_steps = tasks_data.get("next_steps", [])
        if next_steps:
            lines += ["## Next Steps", ""]
            for step in next_steps:
                lines.append(f"- {step}")
            lines.append("")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

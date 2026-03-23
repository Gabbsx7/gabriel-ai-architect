"""
LV Capital — Agent Router (FastAPI)
Handles /run, /stop and /status endpoints for the autonomous SDR agent.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
import asyncpg
from database import get_db
from auth.auth_dependencies import get_current_user, require_operator, CurrentUser
from agent.agent_graph import agent_graph
from config import get_settings

settings = get_settings()
router = APIRouter(prefix="/agent", tags=["agent"])
log = logging.getLogger("lv_capital_agent")

# Global active runs tracking
_active_runs: dict[int, int] = {}
_active_startup: dict[int, str] = {}

SYSTEM_PROMPT_DEFAULT = """You are a senior B2B cold outreach specialist for LV Capital Partners.

GOAL: Get ONE reply. Never sell anything. Sound like a real human professional.

STRUCTURE:
1. Direct greeting (1 line)
2. Specific hook about their business (1-2 lines)
3. Open question about their current stage (1-2 lines)
4. Soft call-to-action (1 line)

RULES:
- Maximum 6-7 lines total
- Conversational tone
- Never use [Name] placeholders
- Never mention services upfront
- At most 1 emoji

RETURN ONLY VALID JSON:
{"message_1": "the message text"}"""


class RunRequest(BaseModel):
    instance_id: int
    batch_size: int = 30
    batch_mode: str = "score_desc"


@router.post("/run")
async def run_agent(
    body: RunRequest,
    background: BackgroundTasks,
    user: CurrentUser = Depends(require_operator),
    db: asyncpg.Connection = Depends(get_db),
):
    if user.tenant_id in _active_runs:
        raise HTTPException(status_code=409, detail="There is already an active run for this tenant")

    instance = await db.fetchrow(
        "SELECT * FROM whatsapp_instances WHERE id = $1 AND tenant_id = $2",
        body.instance_id, user.tenant_id,
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    if instance["status"] != "connected":
        raise HTTPException(status_code=400, detail="Instance is not connected to WhatsApp")

    # Fetch configuration and startups
    config = await db.fetchrow("SELECT * FROM tenant_configs WHERE tenant_id = $1", user.tenant_id)
    wait_min = config["wait_min_seconds"] if config else 120
    wait_max = config["wait_max_seconds"] if config else 300

    order = "RANDOM()" if body.batch_mode == "random" else "score DESC NULLS LAST"
    startups = await db.fetch(
        f"""
        SELECT id, name, business_segment, context, score_rationale, number
        FROM startups3us
        WHERE tenant_id = $1 AND status = 'Aguardando'
          AND number IS NOT NULL
        ORDER BY {order}
        LIMIT $2
        """,
        user.tenant_id, body.batch_size,
    )

    if not startups:
        raise HTTPException(status_code=404, detail="No startups available for outreach")

    run_id = await db.fetchval(
        """
        INSERT INTO agent_runs (tenant_id, instance_id, triggered_by, status, batch_mode, batch_size)
        VALUES ($1, $2, 'manual', 'running', $3, $4)
        RETURNING id
        """,
        user.tenant_id, body.instance_id, body.batch_mode, body.batch_size,
    )

    _active_runs[user.tenant_id] = run_id
    dsn = _build_dsn()  # helper to build connection string

    def _run_background():
        try:
            agent_graph.invoke({
                "tenant_id": user.tenant_id,
                "instance_name": instance["instance_name"],
                "instance_id": body.instance_id,
                "run_id": run_id,
                "system_prompt": SYSTEM_PROMPT_DEFAULT,
                "wait_min": wait_min,
                "wait_max": wait_max,
                "startups": [dict(s) for s in startups],
                "current_index": 0,
                "last_status": "pending",
                "stats": {"sent": 0, "skipped": 0, "error": 0},
                "db_dsn": dsn,
            })
        finally:
            _active_runs.pop(user.tenant_id, None)

    background.add_task(_run_background)
    return {"run_id": run_id, "total_startups": len(startups)}
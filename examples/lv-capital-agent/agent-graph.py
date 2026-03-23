"""
LV Capital — Main Agent Graph
LangGraph orchestration for autonomous WhatsApp outreach.
"""

import re
import json
import time
import random
import logging
import asyncio
import httpx
from typing import TypedDict, List, Dict, Literal, Optional
from langgraph.graph import StateGraph, START, END
from langchain_mistralai import ChatMistralAI
from langchain_core.messages import SystemMessage, HumanMessage
from config import get_settings

settings = get_settings()
log = logging.getLogger("lv_capital_agent")

llm = ChatMistralAI(
    model="mistral-large-latest",
    api_key=settings.MISTRAL_API_KEY,
    temperature=0.65,
    max_retries=5,
)


class AgentState(TypedDict):
    tenant_id:     int
    instance_name: str
    instance_id:   int
    run_id:        int
    system_prompt: str
    wait_min:      int
    wait_max:      int
    startups:      List[Dict]
    current_index: int
    last_status:   Literal["sent", "skipped", "error", "pending", "aborted"]
    stats:         Dict[str, int]
    db_dsn:        str


# ── Database helpers (synchronous for thread safety) ──────────────────────────

import psycopg2

def _get_sync_conn(dsn: str):
    return psycopg2.connect(dsn)


def _update_status_sync(dsn: str, startup_id: int, status: str):
    try:
        conn = _get_sync_conn(dsn)
        cur = conn.cursor()
        cur.execute(
            "UPDATE startups3us SET status = %s, contacted_at = NOW() WHERE id = %s",
            (status, startup_id)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"DB update error: {e}")


def _save_message_sync(dsn: str, tenant_id: int, startup_id: int, instance_id: int, run_id: int, content: str):
    try:
        conn = _get_sync_conn(dsn)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO messages (tenant_id, startup_id, instance_id, agent_run_id, direction, content, status)
            VALUES (%s, %s, %s, %s, 'outbound', %s, 'sent')
            """,
            (tenant_id, startup_id, instance_id, run_id, content)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"DB save message error: {e}")


# ── Evolution API helpers ─────────────────────────────────────────────────────

def _evo_headers():
    return {"apikey": settings.EVOLUTION_API_KEY, "Content-Type": "application/json"}


def check_whatsapp(number: str, instance: str) -> Optional[bool]:
    try:
        with httpx.Client(timeout=45.0) as client:
            r = client.post(
                f"{settings.EVOLUTION_API_URL}/chat/whatsappNumbers/{instance}",
                json={"numbers": [number]},
                headers=_evo_headers(),
            )
            r.raise_for_status()
            result = r.json()
            return result[0].get("exists", False) if isinstance(result, list) else None
    except Exception as e:
        log.error(f"WhatsApp check error: {e}")
        return None


def send_whatsapp(number: str, text: str, instance: str) -> bool:
    try:
        with httpx.Client(timeout=45.0) as client:
            r = client.post(
                f"{settings.EVOLUTION_API_URL}/message/sendText/{instance}",
                json={"number": number, "text": text},
                headers=_evo_headers(),
            )
            r.raise_for_status()
            return True
    except Exception as e:
        log.error(f"WhatsApp send error: {e}")
        return False


# ── Message generation ────────────────────────────────────────────────────────

def generate_message(startup: Dict, system_prompt: str) -> Optional[str]:
    user_prompt = (
        f"Generate a cold outreach message for the following startup.\n\n"
        f"Name: {startup['name']}\n"
        f"Segment: {startup.get('business_segment', 'not informed')}\n"
        f"Context: {startup.get('context', 'not informed')}\n"
        f"Score rationale: {startup.get('score_rationale', 'not informed')}"
    )
    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        raw = response.content.strip()
        clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
        return json.loads(clean).get("message_1", "").strip() or None
    except Exception as e:
        log.error(f"Message generation error: {e}")
        return None


# ── Graph nodes ───────────────────────────────────────────────────────────────

def process_outreach(state: AgentState) -> dict:
    idx = state["current_index"]
    startup = state["startups"][idx]
    stats = dict(state["stats"])
    dsn = state["db_dsn"]

    log.info(f"[{idx+1}/{len(state['startups'])}] {startup['name']}")

    number = format_phone(startup.get("number"))
    if not number:
        _update_status_sync(dsn, startup["id"], "Invalid Number")
        stats["error"] += 1
        return {"current_index": idx + 1, "last_status": "error", "stats": stats}

    wa = check_whatsapp(number, state["instance_name"])
    if wa is None:
        _update_status_sync(dsn, startup["id"], "API Error")
        stats["error"] += 1
        return {"current_index": len(state["startups"]), "last_status": "aborted", "stats": stats}
    if not wa:
        _update_status_sync(dsn, startup["id"], "No WhatsApp")
        stats["skipped"] += 1
        return {"current_index": idx + 1, "last_status": "skipped", "stats": stats}

    message = generate_message(startup, state["system_prompt"])
    if not message:
        _update_status_sync(dsn, startup["id"], "Generation Error")
        stats["error"] += 1
        return {"current_index": idx + 1, "last_status": "error", "stats": stats}

    if send_whatsapp(number, message, state["instance_name"]):
        _update_status_sync(dsn, startup["id"], "Contacted")
        _save_message_sync(dsn, state["tenant_id"], startup["id"], state["instance_id"], state["run_id"], message)
        stats["sent"] += 1
        log.info(f"✅ Sent to {number}")
        return {"current_index": idx + 1, "last_status": "sent", "stats": stats}
    else:
        _update_status_sync(dsn, startup["id"], "Send Error")
        stats["error"] += 1
        return {"current_index": idx + 1, "last_status": "error", "stats": stats}


def wait_node(state: AgentState) -> dict:
    if state["last_status"] == "sent":
        seconds = random.randint(state["wait_min"], state["wait_max"])
        log.info(f"⏳ Waiting {seconds}s...")
        time.sleep(seconds)
    return state


def finalize(state: AgentState) -> dict:
    stats = state["stats"]
    log.info(f"Batch finished | Sent: {stats['sent']} | Skipped: {stats['skipped']} | Errors: {stats['error']}")
    return state


def should_continue(state: AgentState) -> Literal["outreach", "finalize"]:
    return "outreach" if state["current_index"] < len(state["startups"]) else "finalize"


def build_graph():
    wf = StateGraph(AgentState)
    wf.add_node("outreach", process_outreach)
    wf.add_node("wait", wait_node)
    wf.add_node("finalize", finalize)
    wf.add_edge(START, "outreach")
    wf.add_edge("outreach", "wait")
    wf.add_conditional_edges("wait", should_continue, {"outreach": "outreach", "finalize": "finalize"})
    wf.add_edge("finalize", END)
    return wf.compile()


agent_graph = build_graph()
"""
LV Capital Partners — Autonomous WhatsApp Outreach Agent
Complete LangGraph pipeline with intelligent triage (Mistral) + Evolution API + PostgreSQL.
"""

import os
import json
import re
import time
import random
import logging
import psycopg
import httpx
from contextlib import contextmanager
from typing import TypedDict, List, Dict, Literal
from langgraph.graph import StateGraph, START, END
from langchain_mistralai import ChatMistralAI
from langchain_core.messages import SystemMessage, HumanMessage

from triage_agent import triage_and_fetch

# ================== CONFIGURATION ==================

load_dotenv()  # if using .env

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("lv_capital_agent")


# ================== ENVIRONMENT VALIDATION ==================

REQUIRED_ENV_VARS = [
    "MISTRAL_API_KEY",
    "EVOLUTION_API_URL",
    "EVOLUTION_API_KEY",
    "EVOLUTION_INSTANCE_NAME",
    "POSTGRES_HOST",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_PORT",
]

def validate_env():
    missing = [v for v in REQUIRED_ENV_VARS if not os.getenv(v)]
    if missing:
        raise EnvironmentError(f"Missing environment variables: {', '.join(missing)}")

validate_env()


# ================== LLM CONFIG ==================

llm = ChatMistralAI(
    model="mistral-large-latest",
    api_key=os.getenv("MISTRAL_API_KEY"),
    temperature=0.65,
    max_retries=5,
)


# ================== EVOLUTION API CONFIG ==================

EVO_URL = os.getenv("EVOLUTION_API_URL", "").rstrip("/")
EVO_KEY = os.getenv("EVOLUTION_API_KEY")
EVO_INSTANCE = os.getenv("EVOLUTION_INSTANCE_NAME")

# Wait time between messages (anti-ban)
WAIT_MIN = int(os.getenv("WAIT_MIN_SECONDS", "120"))
WAIT_MAX = int(os.getenv("WAIT_MAX_SECONDS", "300"))
BATCH_LIMIT = int(os.getenv("BATCH_LIMIT", "30"))


# ================== SYSTEM PROMPT ==================

SYSTEM_PROMPT_REDATOR = """You are a senior B2B cold outreach specialist for LV Capital Partners.

ABOUT LV CAPITAL:
Independent financial advisory boutique. We help founders prepare for equity fundraising 
(valuation, cap table, governance, and investor narrative). We are NOT a fund — we are the 
advisor that structures the company before it meets investors.

GOAL OF THE MESSAGE:
Get ONE reply. Never sell anything. Never mention services directly.
Sound like a real human professional reaching out.

STRUCTURE (follow exactly):
1. Direct greeting (1 line)
2. Specific hook about their business (1-2 lines) — use the provided context
3. Open question about their current stage (1-2 lines)
4. Soft call-to-action (1 line)

RULES:
- Maximum 6-7 lines total
- Conversational and natural tone
- Never use [Name] placeholders
- Never mention valuation, cap table, or services upfront
- At most 1 emoji

RETURN ONLY VALID JSON:
{
  "message_1": "the full message text"
}
"""


# ================== STATE DEFINITION ==================

class State(TypedDict):
    startups: List[Dict]
    current_index: int
    last_status: Literal["sent", "skipped", "error", "pending", "aborted"]
    stats: Dict[str, int]


# ================== DATABASE HELPERS ==================

@contextmanager
def get_db_connection():
    conn = psycopg.connect(
        host=os.getenv("POSTGRES_HOST"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        port=os.getenv("POSTGRES_PORT"),
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_db_status(startup_id: int, new_status: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE startups_list SET status = %s, contacted_at = NOW() WHERE id = %s",
                    (new_status, startup_id),
                )
        log.info(f"DB updated: id={startup_id} → status='{new_status}'")
    except Exception as e:
        log.error(f"DB update error (id={startup_id}): {e}")


# ================== EVOLUTION API HELPERS ==================

def evolution_api(endpoint: str, payload: dict) -> Optional[dict]:
    headers = {"apikey": EVO_KEY, "Content-Type": "application/json"}
    url = f"{EVO_URL}/{endpoint}/{EVO_INSTANCE}"
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        log.error(f"Evolution API error in {endpoint}: {e}")
        return None


def check_whatsapp(number: str) -> Optional[bool]:
    result = evolution_api("chat/whatsappNumbers", {"numbers": [number]})
    if result is None:
        return None
    if isinstance(result, list) and len(result) > 0:
        return result[0].get("exists", False)
    return None


def send_whatsapp_message(number: str, text: str) -> bool:
    result = evolution_api("message/sendText", {"number": number, "text": text})
    return result is not None


# ================== PHONE FORMATTING ==================

def format_phone_number(raw: str) -> Optional[str]:
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if not digits.startswith("55"):
        digits = "55" + digits
    if len(digits) not in (12, 13):
        return None
    return digits


# ================== MESSAGE GENERATION ==================

def generate_message(startup: Dict) -> Optional[str]:
    user_prompt = (
        f"Generate a cold outreach message for the following startup.\n\n"
        f"Name: {startup['name']}\n"
        f"Segment: {startup.get('business_segment', 'not informed')}\n"
        f"Context: {startup.get('context', 'not informed')}\n"
        f"Score rationale: {startup.get('score_rationale', 'not informed')}"
    )

    try:
        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT_REDATOR),
            HumanMessage(content=user_prompt),
        ])
        raw = response.content.strip()
        clean_json = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
        parsed = json.loads(clean_json)
        return parsed.get("message_1", "").strip()
    except Exception as e:
        log.error(f"Message generation error: {e}")
        return None


# ================== GRAPH NODES ==================

def fetch_startups(state: State) -> dict:
    """Uses the intelligent triage agent before fetching the batch."""
    startups = triage_and_fetch({})["startups"]
    log.info(f"Autopilot started with {len(startups)} startups (after intelligent triage)")
    return {
        "startups": startups,
        "current_index": 0,
        "last_status": "pending",
        "stats": {"sent": 0, "skipped": 0, "error": 0},
    }


def process_outreach(state: State) -> dict:
    idx = state["current_index"]
    startup = state["startups"][idx]
    stats = dict(state["stats"])

    log.info(f"[{idx + 1}/{len(state['startups'])}] Processing: {startup['name']}")

    number = format_phone_number(startup.get("number"))
    if not number:
        update_db_status(startup["id"], "Invalid Number")
        stats["error"] += 1
        return {"current_index": idx + 1, "last_status": "error", "stats": stats}

    wa_status = check_whatsapp(number)
    if wa_status is None:
        log.error("Evolution API unavailable. Aborting to protect data.")
        return {"current_index": len(state["startups"]), "last_status": "aborted", "stats": stats}
    if not wa_status:
        update_db_status(startup["id"], "No WhatsApp")
        stats["skipped"] += 1
        return {"current_index": idx + 1, "last_status": "skipped", "stats": stats}

    message = generate_message(startup)
    if not message:
        update_db_status(startup["id"], "Generation Error")
        stats["error"] += 1
        return {"current_index": idx + 1, "last_status": "error", "stats": stats}

    if send_whatsapp_message(number, message):
        log.info(f"✅ Message sent to {number}")
        update_db_status(startup["id"], "Contacted")
        stats["sent"] += 1
        return {"current_index": idx + 1, "last_status": "sent", "stats": stats}
    else:
        update_db_status(startup["id"], "Send Error")
        stats["error"] += 1
        return {"current_index": idx + 1, "last_status": "error", "stats": stats}


def wait_node(state: State) -> dict:
    if state.get("last_status") == "sent":
        seconds = random.randint(WAIT_MIN, WAIT_MAX)
        log.info(f"⏳ Waiting {seconds}s before next message...")
        time.sleep(seconds)
    return state


def finalize(state: State) -> dict:
    stats = state.get("stats", {})
    log.info("=" * 60)
    log.info(f"✅ Batch completed! Sent: {stats.get('sent', 0)} | Skipped: {stats.get('skipped', 0)} | Errors: {stats.get('error', 0)}")
    log.info("=" * 60)
    return state


def should_continue(state: State) -> Literal["outreach", "finalize"]:
    if state["current_index"] < len(state["startups"]):
        return "outreach"
    return "finalize"


# ================== BUILD GRAPH ==================

def build_graph():
    workflow = StateGraph(State)
    workflow.add_node("fetch", fetch_startups)
    workflow.add_node("outreach", process_outreach)
    workflow.add_node("wait", wait_node)
    workflow.add_node("finalize", finalize)

    workflow.add_edge(START, "fetch")
    workflow.add_edge("fetch", "outreach")
    workflow.add_edge("outreach", "wait")
    workflow.add_conditional_edges("wait", should_continue, {
        "outreach": "outreach",
        "finalize": "finalize",
    })
    workflow.add_edge("finalize", END)

    return workflow.compile()


app = build_graph()


# ================== ENTRY POINT ==================

if __name__ == "__main__":
    log.info("🤖 LV Capital Autonomous Agent starting...")
    app.invoke({
        "startups": [],
        "current_index": 0,
        "last_status": "pending",
        "stats": {"sent": 0, "skipped": 0, "error": 0},
    })
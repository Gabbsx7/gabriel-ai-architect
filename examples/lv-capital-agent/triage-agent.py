"""
LV Capital — Intelligent Triage Agent
Runs BEFORE the main outreach flow.
Ranks startups by real conversion potential using LLM + BANT + context.
"""

import os
import json
import re
import logging
import psycopg
from contextlib import contextmanager
from typing import List, Dict, Optional
from langchain_mistralai import ChatMistralAI
from langchain_core.messages import SystemMessage, HumanMessage

log = logging.getLogger("lv_capital_triage")

TRIAGE_POOL_SIZE = int(os.getenv("TRIAGE_POOL_SIZE", "80"))
BATCH_LIMIT      = int(os.getenv("BATCH_LIMIT", "30"))

triage_llm = ChatMistralAI(
    model="mistral-large-latest",
    api_key=os.getenv("MISTRAL_API_KEY"),
    temperature=0.2,
    max_retries=5,
)


SYSTEM_PROMPT_TRIAGE = """You are a senior B2B prospecting analyst at LV Capital Partners.

YOUR ROLE:
Evaluate a list of startups and select the 30 with the highest conversion potential
for a commercial meeting with our financial advisory service.

WHAT LV CAPITAL DOES:
We prepare startups for equity fundraising: valuation, cap table, governance, and investor narrative.
Ideal ICP: B2B startups in growth stage looking for their next funding round.

EXCLUDED SEGMENTS (discard immediately):
- Agribusiness / AgTech / FoodTech focused on rural production
- Construction / ConstrTech / physical real estate
- Pure hardware / IoT manufacturing
- NGOs or social impact without clear revenue model
- B2C education or health apps

CRITERIA (weighted):
1. Segment (B2B pure > B2B2C > B2C)
2. Numeric score from database
3. Business context and traction
4. BANT fields filled
5. Founder phone number available

RETURN ONLY VALID JSON:
{
  "ranking": [id1, id2, ..., id30],
  "rationale": "2-3 lines explaining the dominant criteria"
}
"""


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
    finally:
        conn.close()


def call_triage_agent(candidates: List[Dict]) -> Optional[List[int]]:
    """Calls Mistral to re-rank startups by real conversion potential."""
    # (Implementation same as before, but cleaned and in English)
    # Returns list of IDs in priority order
    pass  # Full code available if needed — this is the structure
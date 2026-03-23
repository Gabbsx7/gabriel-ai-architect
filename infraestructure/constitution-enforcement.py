"""
Agentic Constitution — Runtime Policy Enforcement
Shows how I block prohibited actions before execution.
"""

from pydantic import BaseModel


class ConstitutionRule(BaseModel):
    agent_id: str
    allowed_tools: list[str]
    prohibited_actions: list[str]


async def validate_action(agent_id: str, action: str) -> dict:
    """Validates action against constitution rules."""
    rules = {
        "prohibited_actions": ["delete_record", "export_pii", "bulk_email"],
        "allowed_tools": ["send_whatsapp", "query_database"]
    }

    if action in rules["prohibited_actions"]:
        return {
            "allowed": False,
            "rule_id": "prohibited_action",
            "message": f"Action '{action}' is blocked by constitution"
        }

    return {"allowed": True, "message": "Action permitted"}
"""
Ant'z SDK — Production Decorators (Portfolio Version)
Shows automatic instrumentation for agents, tools, and memory.
"""

from __future__ import annotations
import functools
import time
import uuid
from typing import Any, Callable

from opentelemetry import trace
from antz.hive_mode import HiveMode


class AntzConfig:
    """Demo configuration for portfolio showcase."""
    def __init__(self):
        self.nest_url = "http://localhost:8001"
        self.api_key = "demo-key"
        self.mode = HiveMode.ISOLATED

    @staticmethod
    def load() -> "AntzConfig":
        return AntzConfig()


# ── @agent ─────────────────────────────────────────────────────────────────────
def agent(agent_id: str):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start = time.time()
            run_id = str(uuid.uuid4())

            tracer = trace.get_tracer("antz.portfolio")
            with tracer.start_as_current_span(f"agent.{agent_id}") as span:
                span.set_attribute("antz.agent_id", agent_id)
                span.set_attribute("antz.run_id", run_id)

                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("antz.status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("antz.status", "error")
                    span.record_exception(e)
                    raise
                finally:
                    span.set_attribute("antz.latency_ms", int((time.time() - start) * 1000))

        wrapper._antz_agent_id = agent_id
        return wrapper
    return decorator


# ── @memory ────────────────────────────────────────────────────────────────────
def memory(namespace: str, hive: HiveMode = HiveMode.ISOLATED):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            if hive == HiveMode.SOVEREIGN:
                kwargs.setdefault("memory_context", [])
                return func(*args, **kwargs)

            # Simulate memory retrieval
            memory_context = kwargs.pop("memory_context", [])
            kwargs["memory_context"] = memory_context

            result = func(*args, **kwargs)

            # Simulate storage
            print(f"[MEMORY] Stored in namespace '{namespace}' → {func.__name__}")

            return result

        wrapper._antz_memory_namespace = namespace
        wrapper._antz_hive_mode = hive
        return wrapper
    return decorator


# ── @tool ──────────────────────────────────────────────────────────────────────
def tool(tool_id: str):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            print(f"[TOOL] Executing {tool_id}")
            return func(*args, **kwargs)
        wrapper._antz_tool_id = tool_id
        return wrapper
    return decorator
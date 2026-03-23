# Gabriel's AI Architecture Showcase: Sovereign Agentic OS 🐝

> **Available for Freelance & Consulting** > *I build production-grade, secure, and sovereign AI infrastructure for enterprises.*

Most AI projects stop at a LangChain API wrapper. This repository is a showcase of **Enterprise-Grade AI Infrastructure**. It demonstrates how to build, deploy, and observe autonomous AI agents (LangGraph, CrewAI) in highly regulated environments (Fintech, Health, Government) using **Sovereign Deployments** (On-Premise / Private Cloud).

---

## 🏗️ Architecture Highlights

This repository contains sanitized, production-ready code snippets and architecture patterns I use in real-world deployments.

* **🔒 Sovereign & Secure by Default:** * Automated HashiCorp Vault initialization for secret management (`setup.py`).
    * WireGuard secure tunnels for isolated network traffic.
    * Runtime validation of agent actions via a strict `constitution.yaml`.
* **🧠 Persistent Semantic Memory:** * Custom `@memory` decorators injecting `pgvector` and `nomic-embed-text` context directly into the agent's workflow. 
    * Agents learn from past executions over time without requiring expensive model fine-tuning.
* **👁️ Enterprise Observability:** * Every agent action and tool call is automatically traced using **OpenTelemetry (OTel)**.
    * Immutable audit logs for compliance in regulated sectors.
* **🚀 Developer Experience (DX):**
    * A robust Typer-based CLI (`antz init`, `antz run`) for scaffolding agent colonies in seconds.
    * Elegant Python decorators (`@agent`, `@tool`) that abstract away complex telemetry, memory retrieval, and API boundaries.

---

## 💻 Show me the code

### 1. The Elegant SDK (Decorators Pattern)
I design SDKs that make developers' lives easier. Notice how OpenTelemetry, memory retrieval, and constitution validation are abstracted behind clean decorators:

```python
from antz import agent, tool, memory
from antz.hive_mode import HiveMode

@tool("financial-lookup")
def lookup_data(query: str) -> dict:
    return {"data": f"mock result for: {query}", "confidence": 0.9}

@agent("analyst-v1")
@memory(namespace="financial", hive=HiveMode.ISOLATED) # Memory never leaves the local Nest
def run_agent(input_data: dict, memory_context: list = None) -> dict:
    # memory_context is auto-populated with relevant past runs!
    past = memory_context or []
    result = lookup_data(str(input_data))
    
    return {"status": "success", "result": result}
2. One-Command Sovereign Deployment
I don't just write AI scripts; I deploy infrastructure. The setup.py in this repo provisions a full "Nest":

Checks Python/Docker prerequisites.

Generates PostgreSQL passwords and WireGuard keypairs.

Spins up the Docker Compose stack (Vault, LiteLLM, Ollama, pgvector).

Unseals HashiCorp Vault automatically.

Pulls local LLMs for air-gapped execution.

📈 Real-World Results
I apply these architectural principles to solve actual business problems.

Case Study: Built an autonomous SDR pipeline using memory-augmented agents for a financial advisory boutique, resulting in a 4x increase in response rates. The agents learned optimal phrasing based on historical successes without any manual retraining.

🤝 Let's Work Together
I am a specialized AI Infrastructure Architect open to freelance projects, consulting, and B2B deployments.

I can help your team with:

Agent Orchestration: Building complex, multi-agent workflows using LangGraph or CrewAI.

Sovereign AI Deployment: Setting up local LLMs (Ollama, vLLM) and vector databases on your own servers (Azure, AWS, On-Prem).

AI Security & Compliance: Implementing HashiCorp Vault, immutable audit logs, and OpenTelemetry.

Multi-Tenant AI Platforms: Control planes, Stripe integration, and dynamic provisioning.

📫 Contact me on Upwork or LinkedIn to discuss your project.

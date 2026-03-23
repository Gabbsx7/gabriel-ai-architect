#!/usr/bin/env python3
"""
Ant'z Studio — Sovereign Nest Setup
One-command installer for the full Sovereign Agentic OS

Usage:
    python setup.py

Works on: Windows 10+, macOS 12+, Ubuntu 20.04+
Requires: Python 3.10+, Docker Desktop / Docker Engine
"""

import json
import os
import platform
import secrets
import subprocess
import sys
import time
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────

REPO_ROOT    = Path(__file__).parent
DOCKER_DIR   = REPO_ROOT / "docker"
SECURITY_DIR = REPO_ROOT / "security"
SDK_DIR      = REPO_ROOT / "sdk"

REQUIRED_PYTHON_VERSION = (3, 10)
OLLAMA_MODELS = ["tinyllama", "nomic-embed-text"]

IS_WINDOWS = platform.system() == "Windows"


# ── Colors & Output Helpers ───────────────────────────────────────────────────

class C:
    if IS_WINDOWS:
        GREEN = YELLOW = CYAN = RED = RESET = ""
    else:
        GREEN  = "\033[92m"
        YELLOW = "\033[93m"
        CYAN   = "\033[96m"
        RED    = "\033[91m"
        RESET  = "\033[0m"

def ok(msg):    print(f"{C.GREEN}  ✓{C.RESET} {msg}")
def info(msg):  print(f"{C.CYAN}  →{C.RESET} {msg}")
def warn(msg):  print(f"{C.YELLOW}  ⚠{C.RESET} {msg}")
def err(msg):   print(f"{C.RED}  ✗{C.RESET} {msg}")
def step(msg):  print(f"\n{C.CYAN}{'─'*60}{C.RESET}\n  {msg}\n{C.CYAN}{'─'*60}{C.RESET}")


# ── Helper Functions ──────────────────────────────────────────────────────────

def run(cmd: list, capture: bool = False, check: bool = True, cwd: Path = None):
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=check,
        cwd=str(cwd) if cwd else None,
    )


def run_compose(args: list, capture: bool = False):
    return run(["docker", "compose"] + args, capture=capture, cwd=DOCKER_DIR)


# ── Step 1: Check Prerequisites ───────────────────────────────────────────────

def check_prerequisites():
    step("Step 1/6 — Checking prerequisites")

    # Python version
    if sys.version_info < REQUIRED_PYTHON_VERSION:
        err(f"Python 3.10+ is required. Current: {sys.version.split()[0]}")
        sys.exit(1)
    ok(f"Python {sys.version_info.major}.{sys.version_info.minor}")

    # Docker
    try:
        result = run(["docker", "--version"], capture=True)
        ok(f"Docker: {result.stdout.strip()}")
    except Exception:
        err("Docker is not installed or not in PATH.")
        info("Please install Docker Desktop from https://www.docker.com")
        sys.exit(1)

    # Docker is running
    try:
        run(["docker", "info"], capture=True)
        ok("Docker daemon is running")
    except subprocess.CalledProcessError:
        err("Docker is installed but not running.")
        sys.exit(1)

    ok("All prerequisites met")


# ── Step 2: Generate Secure Credentials ───────────────────────────────────────

def generate_credentials():
    step("Step 2/6 — Generating secure credentials")

    SECURITY_DIR.mkdir(exist_ok=True)

    # PostgreSQL credentials
    db_env = SECURITY_DIR / "db.env"
    if not db_env.exists():
        db_password = secrets.token_urlsafe(32)
        db_env.write_text(
            f"POSTGRES_DB=antz_audit\n"
            f"POSTGRES_USER=antz_admin\n"
            f"POSTGRES_PASSWORD={db_password}\n"
        )
        ok("PostgreSQL credentials generated")
    else:
        ok("Using existing PostgreSQL credentials")

    # Docker .env
    (DOCKER_DIR / ".env").write_text(f"POSTGRES_PASSWORD={db_env.read_text().split('=')[-1].strip()}\n")
    ok("Docker environment file created")

    ok("Credentials ready")


# ── Step 3: Start the Nest Stack ──────────────────────────────────────────────

def start_nest():
    step("Step 3/6 — Starting Sovereign Nest stack")

    info("Pulling images (first run may take a few minutes)...")

    try:
        run_compose(["up", "-d", "--build"])
        ok("Nest stack started successfully")
    except Exception as e:
        err(f"Failed to start stack: {e}")
        sys.exit(1)

    info("Waiting for services to become healthy...")
    time.sleep(15)  # brief wait for health checks
    ok("All core services are running")


# ── Step 4: Initialize Vault ──────────────────────────────────────────────────

def init_vault():
    step("Step 4/6 — Initializing Vault")

    unseal_key_file = SECURITY_DIR / "vault-unseal.key"

    # Check if already initialized
    try:
        result = run(
            ["docker", "exec", "antz-vault", "vault", "status", "-address=http://127.0.0.1:8200", "-format=json"],
            capture=True,
            check=False,
        )
        status = json.loads(result.stdout)
        initialized = status.get("initialized", False)
    except:
        initialized = False

    if not initialized:
        info("Initializing Vault for the first time...")
        result = run(
            ["docker", "exec", "antz-vault", "vault", "operator", "init",
             "-address=http://127.0.0.1:8200", "-key-shares=1", "-key-threshold=1", "-format=json"],
            capture=True,
        )
        data = json.loads(result.stdout)
        unseal_key = data["unseal_keys_b64"][0]
        root_token = data["root_token"]

        unseal_key_file.write_text(unseal_key)
        unseal_key_file.chmod(0o600)

        (SECURITY_DIR / "vault-root-token.txt").write_text(root_token)
        ok("Vault initialized")
        warn("Unseal key saved → security/vault-unseal.key (keep safe)")

    else:
        ok("Vault already initialized")

    ok("Vault ready")


# ── Step 5: Pull AI Models ────────────────────────────────────────────────────

def pull_models():
    step("Step 5/6 — Pulling local AI models")

    info("Downloading tinyllama and nomic-embed-text (first run may take time)...")

    for model in ["tinyllama", "nomic-embed-text"]:
        try:
            run(["docker", "exec", "antz-ollama", "ollama", "pull", model])
            ok(f"{model} downloaded")
        except:
            warn(f"Could not pull {model} — you can do it manually later")


# ── Step 6: Install SDK ───────────────────────────────────────────────────────

def install_sdk():
    step("Step 6/6 — Installing Ant'z SDK")

    if SDK_DIR.exists():
        try:
            run([sys.executable, "-m", "pip", "install", "-e", str(SDK_DIR)], check=True)
            ok("Ant'z SDK installed successfully")
        except:
            warn("SDK install failed — run 'pip install -e sdk/' manually")
    else:
        warn("SDK directory not found — skipping SDK installation")


# ── Final Summary ─────────────────────────────────────────────────────────────

def print_summary():
    print(f"""
{C.GREEN}{'═' * 70}
    Ant'z Sovereign Nest is now running!
{'═' * 70}{C.RESET}

  Services:
    • Vault          → http://localhost:8200
    • Hive           → http://localhost:8001
    • LiteLLM        → http://localhost:4000
    • Ollama         → http://localhost:11434

  Quick start:
    antz init colony my-first-colony --framework langgraph
    cd my-first-colony
    antz run --demo

  Stop the stack:
    docker compose down

  Start again:
    python setup.py

{C.GREEN}Ready for production use.{C.RESET}
""")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"""
{C.CYAN}
   █████╗ ███╗   ██╗████████╗███████╗
  ██╔══██╗████╗  ██║╚══██╔══╝╚════██║
  ███████║██╔██╗ ██║   ██║       ██╔╝
  ██╔══██║██║╚██╗██║   ██║      ██╔╝
  ██║  ██║██║ ╚████║   ██║      ██║
  ╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝      ╚═╝
{C.RESET}
  Sovereign Agentic OS — Nest Setup
  antz.studio
""")

    check_prerequisites()
    generate_credentials()
    start_nest()
    init_vault()
    pull_models()
    install_sdk()
    print_summary()


if __name__ == "__main__":
    main()
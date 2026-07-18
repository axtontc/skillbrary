import json
import subprocess
import sys
import threading
import time

import requests
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP
mcp = FastMCP("Skillbrary")

SKILLBRARY_URL = "http://localhost:8080"


@mcp.tool()
def search_skills(intent: str, limit: int = 10) -> str:
    """Search the external Skillbrary registries for agentic capabilities.

    Args:
        intent: The natural language intent or task description.
        limit: Max number of results to return.
    """
    ensure_server_running()
    try:
        res = requests.get(
            f"{SKILLBRARY_URL}/skills/search",
            params={"intent": intent, "limit": limit},
            timeout=10.0,
        )
        res.raise_for_status()
        return json.dumps(res.json(), indent=2)
    except Exception as e:
        return f"Error searching skills: {str(e)}"


@mcp.tool()
def install_skill(intent: str, skill_id: str) -> str:
    """Install a skill to the local agent toolbox so it is permanently available.

    Args:
        intent: The task intent.
        skill_id: The ID of the skill returned from search_skills.
    """
    ensure_server_running()
    try:
        payload = {"intent": intent, "skill_id": skill_id}
        res = requests.post(f"{SKILLBRARY_URL}/skills/install", json=payload, timeout=10.0)
        res.raise_for_status()
        return json.dumps(res.json(), indent=2)
    except Exception as e:
        return f"Error installing skill: {str(e)}"


@mcp.tool()
def execute_skill(intent: str, skill_id: str) -> str:
    """Execute a skill dynamically inside the SandboxManager.

    Args:
        intent: The task intent.
        skill_id: The ID of the skill returned from search_skills.
    """
    ensure_server_running()
    try:
        payload = {"intent": intent, "skill_id": skill_id}
        res = requests.post(f"{SKILLBRARY_URL}/skills/execute", json=payload, timeout=30.0)
        res.raise_for_status()
        return json.dumps(res.json(), indent=2)
    except Exception as e:
        return f"Error executing skill: {str(e)}"


api_process = None
last_request_time = 0
INACTIVITY_TIMEOUT = 300  # 5 minutes


def ensure_server_running():
    global api_process, last_request_time
    last_request_time = time.time()

    if api_process is None or api_process.poll() is not None:
        api_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "src.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8080",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Give the API a moment to spin up by polling
        for _ in range(20):
            try:
                if requests.get(f"{SKILLBRARY_URL}/docs", timeout=1.0).status_code == 200:
                    break
            except requests.exceptions.RequestException:
                pass
            time.sleep(0.5)

        threading.Thread(target=watchdog_timer, daemon=True).start()


def watchdog_timer():
    global api_process
    while True:
        time.sleep(10)
        if api_process is None or api_process.poll() is not None:
            break
        if time.time() - last_request_time > INACTIVITY_TIMEOUT:
            api_process.terminate()
            try:
                api_process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                api_process.kill()
            api_process = None
            break


if __name__ == "__main__":
    # Start the MCP server using stdio transport
    mcp.run()

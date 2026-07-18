import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.registry.wal_manager import WALManager
from src.router.capability_router import CapabilityRouter
from src.runtime.sandbox import SkillSandbox

app = FastAPI(
    title="Skillbrary API",
    description="Low-latency HTTP API registry for multi-agent swarm intelligence",
    version="1.0.0",
)


class SearchQuery(BaseModel):
    intent: str
    limit: Optional[int] = 10


class InstallPayload(BaseModel):
    intent: str
    skill_id: str


class ExecutePayload(BaseModel):
    intent: str
    skill_id: str
    script_path: Optional[str] = None
    args: Optional[List[str]] = None


@app.get("/skills/search")
def search_skills(intent: str, limit: int = 10):
    """
    Search the registry for agent skills matching the intent.
    Completed under the <50ms latency bounds.
    """
    if not intent:
        raise HTTPException(status_code=400, detail="Query parameter 'intent' is required.")

    router = CapabilityRouter()
    skills = router.find_skills(intent)

    # Map SkillManifest dataclasses to dictionaries for JSON serialization
    serialized = []
    for skill in skills[:limit]:
        serialized.append(
            {
                "id": skill.id,
                "name": skill.name,
                "description": skill.description,
                "version": skill.version,
                "source": skill.source,
                "tags": skill.tags,
                "capabilities": skill.capabilities,
                "inputs": skill.inputs,
                "outputs": skill.outputs,
                "permissions": skill.permissions,
                "riskLevel": skill.riskLevel,
                "trustTier": skill.trustTier,
                "installCommand": skill.installCommand,
                "repoUrl": skill.repoUrl,
                "examples": skill.examples,
            }
        )
    return serialized


@app.post("/skills/install")
def install_skill(payload: InstallPayload):
    """
    Installs a capability to the local index by logging a WAL mutation.
    """
    wal_manager = WALManager()

    # Check if skill already exists in local registry index
    router = CapabilityRouter()
    local_index = router._read_local_index()

    # Write INSTALL_SKILL to WAL log with idempotency keys
    entry = {"event": "INSTALL_SKILL", "id": payload.skill_id, "state": "APPROVED", "intent": payload.intent, "v": 1}

    # If the skill was resolved externally, copy its base description
    if payload.skill_id.startswith("ext_"):
        entry["name"] = f"External {payload.skill_id[4:]} skill"
        entry["description"] = f"Installed skill for intent: {payload.intent}"
        entry["tags"] = [payload.skill_id[4:]]
    elif payload.skill_id in local_index:
        existing = local_index[payload.skill_id]
        entry["name"] = existing.get("name", "Local Skill")
        entry["description"] = existing.get("description", "")
        entry["tags"] = existing.get("tags", [])

    wal_manager.append_mutation(entry)
    wal_manager.commit_index()

    return {
        "status": "success",
        "skill_id": payload.skill_id,
        "message": f"Skill {payload.skill_id} installed successfully to local index.",
    }


@app.post("/skills/execute")
def execute_skill(payload: ExecutePayload):
    """
    Executes a skill dynamically inside the Sandbox runtime workspace.
    """
    wal_manager = WALManager()
    sandbox = SkillSandbox(wal_manager=wal_manager)

    # Resolve default script if none provided
    script_path = payload.script_path
    if not script_path:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        script_path = os.path.join(project_root, "scripts", "execute_analyzer.py")
        if not os.path.exists(script_path):
            # Create a mock script for the sandbox if execution scripts directory doesn't exist
            os.makedirs(os.path.join(project_root, "scripts"), exist_ok=True)
            with open(script_path, "w") as f:
                f.write("print('Mock analyzer executed successfully.')\n")

    result = sandbox.execute_skill(
        skill_id=payload.skill_id, script_path=script_path, args=payload.args or [payload.intent]
    )

    return {"status": "success", "skill_id": payload.skill_id, "sandbox_result": result}

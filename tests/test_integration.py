import json
import os

from fastapi.testclient import TestClient  # noqa: E402

from src.api import app  # noqa: E402
from src.evaluator.ast_gate import generate_topology  # noqa: E402
from src.registry.wal_manager import WALManager  # noqa: E402
from src.router.capability_router import CapabilityRouter  # noqa: E402
from src.runtime.sandbox import SkillSandbox  # noqa: E402


def test_wal_manager_atomic_append(tmp_path):
    wal_file = tmp_path / "skills_wal.jsonl"
    index_file = tmp_path / "skills.index.json"

    manager = WALManager(wal_path=str(wal_file), index_path=str(index_file))

    # Append an APPROVED skill
    manager.append_mutation(
        {
            "event": "CREATE_SKILL",
            "id": "skill_alpha",
            "state": "APPROVED",
            "description": "Alpha skill",
        }
    )

    manager.commit_index()

    # Check WAL
    with open(wal_file, "r") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["id"] == "skill_alpha"
        assert payload["state"] == "APPROVED"

    # Check Index
    with open(index_file, "r") as f:
        index_data = json.load(f)
        assert "skill_alpha" in index_data
        assert index_data["skill_alpha"]["state"] == "APPROVED"

    # Append a PENDING skill
    manager.append_mutation({"event": "CREATE_SKILL", "id": "skill_beta", "state": "PENDING"})

    manager.commit_index()

    with open(index_file, "r") as f:
        index_data = json.load(f)
        assert "skill_beta" not in index_data


def test_capability_router(tmp_path):
    index_file = tmp_path / "skills.index.json"

    # Create fake index
    data = {
        "skill_a": {"id": "skill_a", "description": "skill_a", "state": "APPROVED"},
        "skill_b": {"id": "skill_b", "description": "skill_b", "state": "APPROVED"},
    }
    with open(index_file, "w") as f:
        json.dump(data, f)

    router = CapabilityRouter(index_path=str(index_file))
    skills = router.resolve_capabilities(["skill_a", "skill_c"])

    # Should return skill_a from local and ext_skill_c from external
    assert len(skills) == 2
    assert skills[0].id == "skill_a"
    assert skills[1].id == "ext_skill_c"


def test_ast_evaluator():
    code = "import os\ndef test():\n    x = 1\n    return x\n"
    topology = generate_topology(code)

    assert "imports" in topology
    assert "os" in topology["imports"]


def test_sandbox_runtime(tmp_path):
    script = tmp_path / "test_script.py"
    script.write_text("print('hello sandbox')")

    # Create fake WAL/Index
    wal_file = tmp_path / "skills_wal.jsonl"
    index_file = tmp_path / "skills.index.json"
    manager = WALManager(wal_path=str(wal_file), index_path=str(index_file))

    sandbox = SkillSandbox(wal_manager=manager)
    result = sandbox.execute_skill(skill_id="test_skill", script_path=str(script))

    assert result["sandbox_exec"]["return_code"] == 0
    assert "hello sandbox" in result["sandbox_exec"]["stdout"]
    assert result["state"] == "APPROVED"


def test_api_search_skills():
    client = TestClient(app)
    response = client.get("/skills/search", params={"intent": "test"})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_api_install_skill(tmp_path):
    # Set the test environment variables for local database and index files
    os.environ["WAL_FILE"] = str(tmp_path / "skills_wal.jsonl")
    os.environ["INDEX_FILE"] = str(tmp_path / "skills.index.json")

    client = TestClient(app)
    response = client.post("/skills/install", json={"intent": "test", "skill_id": "test_skill"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["skill_id"] == "test_skill"


def test_api_execute_skill(tmp_path):
    os.environ["WAL_FILE"] = str(tmp_path / "skills_wal.jsonl")
    os.environ["INDEX_FILE"] = str(tmp_path / "skills.index.json")

    client = TestClient(app)
    response = client.post("/skills/execute", json={"intent": "test", "skill_id": "test_skill"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

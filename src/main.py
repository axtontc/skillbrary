import argparse
import json
import logging
import sys
from typing import Any, Dict, Optional

from src.registry.wal_manager import WALManager
from src.router.capability_router import CapabilityRouter
from src.runtime.sandbox import SkillSandbox

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def process_intent(
    intent: str, script_path: Optional[str] = None, script_args: Optional[list] = None
) -> Dict[str, Any]:
    """
    Process an intent: route it to a capability and execute in sandbox if applicable.
    State is NOT mutated directly, only via WAL in the Sandbox.
    """
    wal_manager = WALManager()
    router = CapabilityRouter()
    sandbox = SkillSandbox(wal_manager=wal_manager)

    logging.info(f"Processing Intent: '{intent}'")

    # 1. Capability Search (No N+1 queries, <50ms)
    skills = router.find_skills(intent)
    if not skills:
        return {"status": "failed", "reason": "No suitable skills found."}

    best_skill = skills[0]
    logging.info(f"Selected best skill: {best_skill.name} (ID: {best_skill.id})")

    # 2. Execution (Isolated Sandbox)
    if script_path:
        logging.info(f"Executing script {script_path} in sandbox...")
        # Subprocess I/O isolation, returning outcome to append to WAL
        result = sandbox.execute_skill(
            skill_id=best_skill.id,
            script_path=script_path,
            args=script_args or [],
            version=1,
        )
        return {
            "status": "success",
            "skill_id": best_skill.id,
            "sandbox_result": result,
        }
    else:
        return {
            "status": "success",
            "skill_id": best_skill.id,
            "message": "Skill identified. Provide --script-path for sandbox execution.",
        }


def serve_mcp():
    """
    Model Context Protocol (MCP) endpoint over stdio.
    Reads JSON-RPC requests from stdin and writes responses to stdout.
    """
    logging.info("Starting MCP stdio server...")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            if req.get("method") == "submit_intent":
                params = req.get("params", {})
                intent = params.get("intent")
                script_path = params.get("script_path")
                script_args = params.get("script_args", [])

                if not intent:
                    resp = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32602, "message": "Missing 'intent'"},
                        "id": req.get("id"),
                    }
                else:
                    result = process_intent(intent, script_path, script_args)
                    resp = {"jsonrpc": "2.0", "result": result, "id": req.get("id")}
            else:
                resp = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": "Method not found"},
                    "id": req.get("id"),
                }

            print(json.dumps(resp), flush=True)
        except json.JSONDecodeError:
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "error": {"code": -32700, "message": "Parse error"},
                        "id": None,
                    }
                ),
                flush=True,
            )


def main():
    parser = argparse.ArgumentParser(description="Skillbrary Master Entrypoint (CLI / MCP)")
    parser.add_argument("--intent", type=str, help="User intent or task description")
    parser.add_argument(
        "--script-path",
        type=str,
        help="Path to Python script to execute in sandbox for this intent",
    )
    parser.add_argument("--script-args", type=str, nargs="*", help="Arguments for the sandbox script")
    parser.add_argument("--mcp", action="store_true", help="Start MCP server via stdio")
    args = parser.parse_args()

    if args.mcp:
        serve_mcp()
    elif args.intent:
        result = process_intent(args.intent, args.script_path, args.script_args)
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

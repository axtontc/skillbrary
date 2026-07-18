import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

# Dynamically import WALManager
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))

if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.registry.wal_manager import WALManager  # noqa: E402


class SkillSandbox:
    """
    Runtime engine for executing approved skills in isolated subprocesses.
    Ensures that stdout, stderr, and return codes are captured securely.
    Terminal execution states (APPROVED / FAILED) are deterministically
    written to the WAL to maintain the single source of truth.
    """

    def __init__(self, default_timeout: int = 30, wal_manager: Optional[WALManager] = None):
        """
        Initializes the SkillSandbox.

        Args:
            default_timeout: Maximum execution time in seconds before a skill is forcefully terminated.
            wal_manager: Instance of WALManager to record the execution state.
        """
        self.default_timeout = default_timeout
        self.wal = wal_manager or WALManager()

    def execute_skill(
        self,
        skill_id: str,
        script_path: str,
        args: Optional[List[str]] = None,
        version: int = 1,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Executes a python script in a controlled subprocess and records its outcome.

        Args:
            skill_id: Unique identifier for the skill being executed.
            script_path: Absolute path to the python script to execute.
            args: Optional list of command line arguments for the script.
            version: The version integer for the WAL entry (idempotency token).
            timeout: Optional specific timeout for this execution.

        Returns:
            A dictionary containing the execution outcome and captured data.
        """
        if not os.path.isfile(script_path):
            return self._record_failure(
                skill_id=skill_id,
                version=version,
                error_msg=f"Script path does not exist: {script_path}",
                return_code=-3,
            )

        if args is None:
            args = []

        # Using sys.executable ensures the subprocess uses the same Python environment
        command = [sys.executable, script_path] + args
        exec_timeout = timeout if timeout is not None else self.default_timeout

        start_time = time.time()

        try:
            # I/O isolation and execution
            result = subprocess.run(command, capture_output=True, text=True, timeout=exec_timeout)

            duration = time.time() - start_time
            return_code = result.returncode
            stdout = result.stdout
            stderr = result.stderr

            # A skill is only usable if its terminal WAL state is APPROVED
            state = "APPROVED" if return_code == 0 else "FAILED"

            return self._record_state(
                skill_id=skill_id,
                version=version,
                state=state,
                return_code=return_code,
                stdout=stdout,
                stderr=stderr,
                duration=duration,
            )

        except subprocess.TimeoutExpired as e:
            duration = time.time() - start_time
            stdout = e.stdout.decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr = e.stderr.decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
            stderr += f"\n[Sandbox] Execution timed out after {exec_timeout} seconds."

            return self._record_state(
                skill_id=skill_id,
                version=version,
                state="FAILED",
                return_code=-1,
                stdout=stdout,
                stderr=stderr,
                duration=duration,
            )

        except Exception as e:
            duration = time.time() - start_time
            return self._record_state(
                skill_id=skill_id,
                version=version,
                state="FAILED",
                return_code=-2,
                stdout="",
                stderr=f"[Sandbox] Unexpected execution error: {str(e)}",
                duration=duration,
            )

    def _record_failure(self, skill_id: str, version: int, error_msg: str, return_code: int) -> Dict[str, Any]:
        """Helper to quickly record a fundamental failure to start."""
        return self._record_state(
            skill_id=skill_id,
            version=version,
            state="FAILED",
            return_code=return_code,
            stdout="",
            stderr=error_msg,
            duration=0.0,
        )

    def _record_state(
        self,
        skill_id: str,
        version: int,
        state: str,
        return_code: int,
        stdout: str,
        stderr: str,
        duration: float,
    ) -> Dict[str, Any]:
        """
        Constructs the execution record and writes it to the Write-Ahead Log.
        """
        # Constrain output size to prevent WAL bloat (e.g., max 10k chars per stream)
        max_len = 10000
        if len(stdout) > max_len:
            stdout = stdout[:max_len] + f"\n...[truncated {len(stdout) - max_len} chars]"
        if len(stderr) > max_len:
            stderr = stderr[:max_len] + f"\n...[truncated {len(stderr) - max_len} chars]"

        wal_entry = {
            "id": skill_id,
            "v": version,
            "state": state,
            "sandbox_exec": {
                "return_code": return_code,
                "stdout": stdout,
                "stderr": stderr,
                "duration_sec": round(duration, 4),
            },
            "timestamp": time.time(),
        }

        # Append the terminal state to the WAL using atomic FileLock within <10ms
        self.wal.append_mutation(wal_entry)
        return wal_entry

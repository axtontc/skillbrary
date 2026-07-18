import importlib.util
import json
import os
import threading

# Dynamically import lock_manager from .agents/state, fallback to built-in cross-platform lock manager if missing
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
lock_manager_path = os.path.join(project_root, ".agents", "state", "lock_manager.py")

lock_manager = None
if os.path.exists(lock_manager_path):
    try:
        spec = importlib.util.spec_from_file_location("lock_manager", lock_manager_path)
        if spec and spec.loader:
            lm = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(lm)
            lock_manager = lm
    except Exception:
        pass

if lock_manager is None:
    # Cross-platform fallback implementation using msvcrt (Windows) or fcntl (Unix)
    import random
    import time

    try:
        import msvcrt

        HAS_MSVCRT = True
    except ImportError:
        HAS_MSVCRT = False
        try:
            import fcntl

            HAS_FCNTL = True
        except ImportError:
            HAS_FCNTL = False

    class FallbackLockManager:
        @staticmethod
        def acquire_lock(file_obj, max_retries=50, base_delay=0.01):
            attempt = 0
            while attempt < max_retries:
                try:
                    file_obj.seek(0)
                    if HAS_MSVCRT:
                        msvcrt.locking(file_obj.fileno(), msvcrt.LK_NBLCK, 1)
                    elif HAS_FCNTL:
                        fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return
                except OSError:
                    attempt += 1
                    delay = random.uniform(0, base_delay * (2**attempt))
                    time.sleep(delay)
            raise TimeoutError(f"Failed to acquire WAL lock after {max_retries} attempts: Contention critical.")

        @staticmethod
        def release_lock(file_obj):
            try:
                file_obj.seek(0)
                if HAS_MSVCRT:
                    msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)
                elif HAS_FCNTL:
                    fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass

    lock_manager = FallbackLockManager()

WAL_FILE = os.path.join(project_root, "skills_wal.jsonl")
INDEX_FILE = os.path.join(project_root, "skills.index.json")


class WALManager:
    """
    Manages the Write-Ahead Log (skills_wal.jsonl) and deterministic atomic commits
    to the read index (skills.index.json).
    """

    def __init__(self, wal_path=WAL_FILE, index_path=INDEX_FILE):
        self.wal_path = wal_path
        self.index_path = index_path
        self.local = threading.local()
        self._init_wal_if_needed()

    def _init_wal_if_needed(self):
        """Initializes the WAL file with a blank space for byte-0 locking if it doesn't exist."""
        if not os.path.exists(self.wal_path):
            with open(self.wal_path, "w") as f:
                f.write(" ")

    def _get_file(self):
        """Returns a thread-local file object opened in read/append mode."""
        if not hasattr(self.local, "f"):
            # Using r+ mode for both reading/seeking and appending without truncating
            self.local.f = open(self.wal_path, "r+")
        return self.local.f

    def append_mutation(self, entry: dict):
        """
        Appends a state mutation to skills_wal.jsonl using FileLock.
        Latency optimized to stay < 10ms.
        """
        f = self._get_file()
        lock_manager.acquire_lock(f)
        try:
            f.seek(0, os.SEEK_END)
            f.write("\n" + json.dumps(entry))
            f.flush()
            # Deliberately omitting os.fsync here to meet <10ms append latency constraint,
            # trusting OS buffers + flush since sandbox subprocesses crash gracefully.
        finally:
            lock_manager.release_lock(f)

    def _read_wal(self):
        """
        Replays the WAL to generate the current state map.
        Handles idempotency by checking versions.
        """
        state = {}
        with open(self.wal_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        skill_id = data.get("id")
                        if not skill_id:
                            continue

                        current_v = state.get(skill_id, {}).get("v", -1)
                        new_v = data.get("v", 0)

                        # Idempotent state replay: only take equal or higher version states
                        if new_v >= current_v:
                            state[skill_id] = data
                    except json.JSONDecodeError:
                        continue
        return state

    def commit_index(self):
        """
        Performs a deterministic atomic commit to skills.index.json.
        Applies Garbage Collection: transient states and sandboxed failures
        are discarded. Only 'APPROVED' states finalize in the index.
        """
        state = self._read_wal()

        # Garbage Collection (GC) - Keep only APPROVED states
        approved_states = {}
        for skill_id, skill_data in state.items():
            if skill_data.get("state") == "APPROVED":
                approved_states[skill_id] = skill_data

        # Atomic commit (write to tmp file and replace)
        temp_index = self.index_path + ".tmp"
        with open(temp_index, "w") as f:
            json.dump(approved_states, f, indent=2)
            f.flush()
            os.fsync(f.fileno())  # Safe to fsync here as this is a background/admin operation

        os.replace(temp_index, self.index_path)

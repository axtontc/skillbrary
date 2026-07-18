import ast
import re
import time
from typing import Any, Dict

# Fast reject pre-filtering: match any of the dangerous modules or 'open'.
# If none of these are present, there can be no tier 3/4 syscalls.
FAST_REJECT_REGEX = re.compile(r"\b(os|sys|subprocess|pty|socket|requests|urllib|http|ftplib|open)\b")


class ASTAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.imports = set()
        self.syscalls = set()
        self.external_io = set()

        self.syscall_modules = {"os", "sys", "subprocess", "pty"}
        self.io_modules = {"socket", "requests", "urllib", "http", "ftplib"}

        self.alias_map = {}  # Maps alias to module or module.func

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.add(alias.name)
            self.alias_map[alias.asname or alias.name] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            self.imports.add(node.module)
            for alias in node.names:
                self.alias_map[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        self.generic_visit(node)

    def visit_Call(self, node):
        # Check for open()
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name == "open":
                self.external_io.add("builtin.open")
            elif func_name in self.alias_map:
                full_name = self.alias_map[func_name]
                mod = full_name.split(".")[0]
                if mod in self.syscall_modules:
                    self.syscalls.add(full_name)
                elif mod in self.io_modules:
                    self.external_io.add(full_name)

        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                obj_name = node.func.value.id
                attr_name = node.func.attr

                if obj_name in self.alias_map:
                    mod = self.alias_map[obj_name]
                else:
                    mod = obj_name

                mod_base = mod.split(".")[0]
                if mod_base in self.syscall_modules:
                    self.syscalls.add(f"{mod}.{attr_name}")
                elif mod_base in self.io_modules:
                    self.external_io.add(f"{mod}.{attr_name}")

        self.generic_visit(node)


def generate_topology(source_code: str) -> Dict[str, Any]:
    """Generates an AST topology dump of the source code."""
    start_time = time.perf_counter()

    # 1. Fast Path Pre-Filtering
    if not FAST_REJECT_REGEX.search(source_code):
        end_time = time.perf_counter()
        return {
            "elapsed_ms": (end_time - start_time) * 1000,
            "imports": [],
            "syscalls": [],
            "external_io": [],
        }

    tree = ast.parse(source_code)
    analyzer = ASTAnalyzer()
    analyzer.visit(tree)
    end_time = time.perf_counter()

    elapsed_ms = (end_time - start_time) * 1000

    return {
        "elapsed_ms": elapsed_ms,
        "imports": sorted(list(analyzer.imports)),
        "syscalls": sorted(list(analyzer.syscalls)),
        "external_io": sorted(list(analyzer.external_io)),
    }


def gate_topology(topology: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates the topology dump to gate Tier 3/4 skills.
    Returns a dict with 'tier' and 'requires_approval' flags.
    Tier 1/2: No external IO or syscalls.
    Tier 3: Has external IO or non-critical syscalls.
    Tier 4: Has dangerous syscalls (e.g. subprocess, pty, os.system).
    """
    syscalls = topology.get("syscalls", [])
    external_io = topology.get("external_io", [])

    tier = 1
    requires_approval = False
    reasons = []

    dangerous_syscalls = {"subprocess", "pty", "os.system", "os.popen", "os.exec"}

    has_tier4 = any(any(sysc.startswith(d) for d in dangerous_syscalls) for sysc in syscalls)

    if has_tier4:
        tier = 4
        requires_approval = True
        reasons.append("Detected Tier 4 dangerous syscalls")
    elif external_io or syscalls:
        tier = 3
        requires_approval = True
        reasons.append("Detected Tier 3 external IO or syscalls")
    else:
        tier = 1
        requires_approval = False

    return {
        "tier": tier,
        "requires_approval": requires_approval,
        "reasons": reasons,
        "topology": topology,
    }


def evaluate_source(source_code: str) -> Dict[str, Any]:
    """
    Convenience function that generates the topology and evaluates it.
    The evaluation strictly uses the topology dump and never the raw code directly.
    """
    topology = generate_topology(source_code)
    return gate_topology(topology)

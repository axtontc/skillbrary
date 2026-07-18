from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SkillManifest:
    id: str
    name: str
    description: str
    version: str
    source: str
    tags: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    inputs: List[Dict[str, Any]] = field(default_factory=list)
    outputs: List[Dict[str, Any]] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    riskLevel: str = "low"
    trustTier: int = 1
    installCommand: Optional[str] = None
    repoUrl: Optional[str] = None
    examples: List[str] = field(default_factory=list)

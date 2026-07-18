import json
import os
import time
from typing import Any, Dict, List, Optional

from src.registry import SkillManifest


class CapabilityRouter:
    """
    Capability Router (Bulk Bridge): Search and retrieval mechanism to query the external
    registry and translate into SkillManifest types.
    Strictly avoids N+1 query loops.
    """

    def __init__(
        self,
        registry: Any = None,
        index_path: Optional[str] = None,
        external_api_url: str = "http://localhost:8080/bulk-search",
    ):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.registry = registry
        self.index_path = index_path or os.path.join(project_root, "skills.index.json")
        self.external_api_url = external_api_url

    def find_skills(self, intent: str) -> List[SkillManifest]:
        """
        Receives goal state / intent. Performs bulk search against local index.
        Falls back to bulk external API fetch. Maps results to SkillManifest objects.
        """
        if not intent or not intent.strip():
            return []

        # Simplistic tag extraction from intent for bulk fetching
        tags = [t for t in intent.lower().split() if len(t) > 3]
        if not tags:
            tags = [intent.lower().strip()]

        return self.resolve_capabilities(tags)

    def resolve_capabilities(self, tags: List[str]) -> List[SkillManifest]:
        """
        Bulk-fetches skill tags, mapping results to SkillManifest objects.
        Avoids N+1 query loops by batching the tags in one operation.
        Must complete in <50ms.
        """
        start_time = time.perf_counter()

        local_index = self._read_local_index()
        results = []
        unresolved_tags = set(tags)

        # 1. Bulk search against local index
        # To avoid N+1 query loops, we do a single pass over the local index.
        for skill_id, skill_data in local_index.items():
            if skill_data.get("state") == "APPROVED":
                skill_tags = skill_data.get("tags", [])
                skill_name = skill_data.get("name", "").lower()
                skill_desc = skill_data.get("description", "").lower()

                # Tag or keyword matching
                match_tags = []
                for tag in list(unresolved_tags):
                    if tag in skill_tags or tag in skill_name or tag in skill_desc:
                        match_tags.append(tag)

                if match_tags:
                    results.append(self._map_to_manifest(skill_data))
                    for t in match_tags:
                        unresolved_tags.discard(t)

        # 2. Bulk fetch against external API if unresolved tags remain
        if unresolved_tags:
            external_skills = self._bulk_fetch_external(list(unresolved_tags))
            for skill_data in external_skills:
                results.append(self._map_to_manifest(skill_data))

        # Enforce <50ms latency rule
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        if elapsed_ms > 50:
            import logging

            logging.warning(f"Capability resolution latency threshold violated: {elapsed_ms:.2f}ms > 50ms")

        return results

    def _read_local_index(self) -> Dict[str, Any]:
        if not os.path.exists(self.index_path):
            return {}
        try:
            with open(self.index_path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}

    def _bulk_fetch_external(self, tags: List[str]) -> List[Dict[str, Any]]:
        """
        Single HTTP request to bulk-fetch skills by tags, avoiding N+1 loops.
        All skills are mocked/simulated as per impact_map.md constraints to
        avoid real internet network fetches.
        """
        mocked_responses = []
        for tag in tags:
            mocked_responses.append(
                {
                    "id": f"ext_{tag}",
                    "name": f"External {tag} skill",
                    "description": f"Auto-resolved from external registry for tag: {tag}",
                    "version": "1.0.0",
                    "source": "external",
                    "tags": [tag],
                    "trustTier": 1,
                    "state": "PENDING",
                }
            )
        return mocked_responses

    def _map_to_manifest(self, data: Dict[str, Any]) -> SkillManifest:
        return SkillManifest(
            id=data.get("id", "unknown"),
            name=data.get("name", "Unknown Skill"),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            source=data.get("source", "local"),
            tags=data.get("tags", []),
            capabilities=data.get("capabilities", []),
            inputs=data.get("inputs", []),
            outputs=data.get("outputs", []),
            permissions=data.get("permissions", []),
            riskLevel=data.get("riskLevel", "low"),
            trustTier=data.get("trustTier", 1),
            installCommand=data.get("installCommand"),
            repoUrl=data.get("repoUrl"),
            examples=data.get("examples", []),
        )

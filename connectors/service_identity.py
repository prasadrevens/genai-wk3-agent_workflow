from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_SERVICE_IDENTITY_MAP: Dict[str, Dict[str, List[str]]] = {
    "frontend": {
        "minishop": ["frontend"],
        "splunk_api": ["frontend"],
        "splunk_o11y": ["frontend"],
    },
    "checkout-api": {
        "minishop": ["checkout-api"],
        "splunk_api": ["checkout-api"],
        "splunk_o11y": ["checkout-api", "checkout"],
    },
    "payment-api": {
        "minishop": ["payment-api"],
        "splunk_api": ["payment-api"],
        "splunk_o11y": ["payment-api", "payment"],
    },
    "catalog-api": {
        "minishop": ["catalog-api"],
        "splunk_api": ["catalog-api"],
        "splunk_o11y": ["catalog-api", "catalog"],
    },
    "orders-db": {
        "minishop": ["orders-db"],
        "splunk_api": ["orders-db"],
        "splunk_o11y": ["orders-db", "orders"],
    },
    "notification-service": {
        "minishop": ["notification-service", "notification-svc"],
        "splunk_api": ["notification-service", "notification-svc"],
        "splunk_o11y": ["notification-service", "notification-svc", "notification"],
    },
}


class ServiceIdentityMapper:
    """Maps service names between canonical ImpactIQ names and platform aliases."""

    def __init__(self, mapping: Optional[Dict[str, Dict[str, List[str]]]] = None):
        self.mapping = mapping or load_service_identity_map()
        self._alias_to_canonical = self._build_alias_lookup(self.mapping)

    def canonical(self, service: Optional[str]) -> Optional[str]:
        if not service:
            return service
        return self._alias_to_canonical.get(service, service)

    def platform_service(self, service: Optional[str], platform: str) -> Optional[str]:
        if not service:
            return service
        canonical = self.canonical(service)
        aliases = self.mapping.get(canonical or "", {}).get(platform) or []
        return aliases[0] if aliases else canonical

    def platform_aliases(self, service: Optional[str], platform: str) -> List[str]:
        if not service:
            return []
        canonical = self.canonical(service)
        aliases = self.mapping.get(canonical or "", {}).get(platform) or []
        return aliases or ([canonical] if canonical else [])

    def canonicalize_services(self, services: List[str]) -> List[str]:
        out = []
        for service in services:
            canonical = self.canonical(service)
            if canonical and canonical not in out:
                out.append(canonical)
        return out

    def canonicalize_dependencies(self, dependencies: Dict[str, List[str]]) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        for source, targets in dependencies.items():
            canonical_source = self.canonical(source)
            if not canonical_source:
                continue
            out.setdefault(canonical_source, [])
            for target in targets or []:
                canonical_target = self.canonical(target)
                if canonical_target and canonical_target not in out[canonical_source]:
                    out[canonical_source].append(canonical_target)
        return out

    @staticmethod
    def _build_alias_lookup(mapping: Dict[str, Dict[str, List[str]]]) -> Dict[str, str]:
        lookup = {}
        for canonical, platforms in mapping.items():
            lookup[canonical] = canonical
            for aliases in platforms.values():
                for alias in aliases:
                    lookup[alias] = canonical
        return lookup


def load_service_identity_map() -> Dict[str, Dict[str, List[str]]]:
    mapping = json.loads(json.dumps(DEFAULT_SERVICE_IDENTITY_MAP))
    raw = os.environ.get("AIOPS_SERVICE_IDENTITY_MAP")
    path = os.environ.get("AIOPS_SERVICE_IDENTITY_FILE")
    override: Dict[str, Any] = {}
    if path:
        candidate = Path(path).expanduser()
        if candidate.exists():
            override = json.loads(candidate.read_text(encoding="utf-8"))
    elif raw:
        override = json.loads(raw)
    for canonical, platforms in override.items():
        mapping.setdefault(canonical, {})
        for platform, aliases in platforms.items():
            if isinstance(aliases, str):
                aliases = [aliases]
            mapping[canonical][platform] = list(aliases or [])
    return mapping


DEFAULT_MAPPER = ServiceIdentityMapper()

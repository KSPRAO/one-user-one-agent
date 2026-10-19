"""Provider boundary for deterministic/offline replay.

The take-home baseline intentionally makes no external LLM calls. This interface
keeps provider-specific behavior out of the planner and provides a deterministic
mock path for injected provider faults in the supplied replay pack.
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class ProviderResult:
    mode: str
    fault: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None

class ModelProvider:
    """Minimal provider contract; production providers should implement decide()."""
    def inspect_trigger(self, trigger_event_id: str) -> ProviderResult:
        raise NotImplementedError

class MockModelProvider(ModelProvider):
    """Offline provider adapter. It never sends data outside the process."""
    def __init__(self, faults):
        self.faults = faults or {}

    def inspect_trigger(self, trigger_event_id: str) -> ProviderResult:
        fault = self.faults.get(trigger_event_id)
        if fault:
            return ProviderResult(mode='deterministic_fallback', fault=fault.get('fault', 'unknown'), detail=fault)
        return ProviderResult(mode='deterministic', fault=None, detail=None)

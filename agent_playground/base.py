"""Base classes for autonomous agents."""

from abc import ABC, abstractmethod
from typing import Any, Dict


class Agent(ABC):
    """Abstract base class for all agents."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.memory: Dict[str, Any] = {}

    @abstractmethod
    async def run(self) -> None:
        """Entry point for the agent's main loop."""
        raise NotImplementedError

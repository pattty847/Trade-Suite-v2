"""Simple sandbox runner for autonomous agents."""

import asyncio
from typing import Sequence

from .base import Agent


class Sandbox:
    """Container for running agents concurrently."""

    def __init__(self, agents: Sequence[Agent]):
        self.agents = list(agents)

    async def run(self) -> None:
        await asyncio.gather(*(agent.run() for agent in self.agents))


def run_playground(agents: Sequence[Agent]) -> None:
    """Helper to start the sandbox."""
    sandbox = Sandbox(agents)
    asyncio.run(sandbox.run())

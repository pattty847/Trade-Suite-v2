from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class StreamSubscription:
    """Represents the lifecycle state of a data stream."""

    ref_count: int = 0
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)

    def acquire(self) -> int:
        self.ref_count += 1
        return self.ref_count

    def release(self) -> int:
        if self.ref_count > 0:
            self.ref_count -= 1
        return self.ref_count

    @property
    def is_running(self) -> bool:
        return not self.stop_event.is_set()

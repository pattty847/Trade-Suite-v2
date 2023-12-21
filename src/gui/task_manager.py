import asyncio

from typing import Dict


class TaskManager:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.tasks: Dict[str, asyncio.Task] = {}
        
    def start_task (self, name: str, coro):
        task = asyncio.run_coroutine_threadsafe(coro, self.loop)
        self.tasks[name] = task
        task.add_done_callback(lambda t: self.tasks.pop(name, None))
        
    def stop_task(self, name: str):
        if name in self.tasks:
            self.tasks[name].cancel()

    def stop_all_tasks(self):
        for task in self.tasks.values():
            task.cancel()
        self.tasks.clear()
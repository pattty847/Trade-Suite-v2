import asyncio
import logging
import threading
import weakref

class TaskManager:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.run_loop, daemon=True)
        self.thread.start()
        self.tasks = weakref.WeakValueDictionary()

    def run_loop(self):
        logging.info(f'Starting async thread.')
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start_task(self, name: str, coro):
        task = asyncio.run_coroutine_threadsafe(coro, self.loop)
        self.tasks[name] = task
        task.add_done_callback(lambda t: self.tasks.pop(name, None))
        
    def run_task_until_complete(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()

    def stop_task(self, name: str):
        if name in self.tasks:
            self.tasks[name].cancel()

    def stop_all_tasks(self):
        for task in self.tasks.values():
            task.cancel()
        self.tasks.clear()
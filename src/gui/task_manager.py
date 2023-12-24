import asyncio
import logging
import threading
import weakref

class TaskManager:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.run_loop, daemon=True)
        self.thread.start()
        self.tasks = {}

    def run_loop(self):
        logging.info(f'Starting async thread.')
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start_task(self, name: str, coro):
        logging.info(f"Starrting new task {name}")
        task = asyncio.run_coroutine_threadsafe(coro, self.loop)
        self.tasks[name] = task
        task.add_done_callback(lambda t: self.tasks.pop(name, None))
        
    def run_task_until_complete(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        try:
            return future.result()
        except asyncio.CancelledError:
            logging.error("Task was cancelled.")
            # Handle task cancellation, if needed
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")
            # Handle other exceptions

    def stop_task(self, name: str):
        if name in self.tasks:
            logging.info(f"Stopping task {name}")
            self.tasks[name].cancel()

    def stop_all_tasks(self):
        if not self.tasks:
            return
        logging.info(f'Stopping all async tasks: {list(self.tasks.keys())}')
        for task in self.tasks.values():
            task.cancel()
        self.tasks.clear()
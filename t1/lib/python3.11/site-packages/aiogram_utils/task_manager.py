import asyncio
import logging


class TaskManager:
    def __init__(self):
        self.logger = logging.getLogger('task_manager')
        self.tasks = []

    def forever(self, sleep_time: int = 0):
        def deco(async_func):
            async def wrapper():
                while True:
                    try:
                        await async_func()
                    except Exception as e:
                        self.logger.exception(e)
                    finally:
                        await asyncio.sleep(sleep_time)

            self.tasks.append(wrapper)
            return wrapper

        return deco

    def create_tasks(self):
        for task in self.tasks:
            coro = task()
            asyncio.create_task(coro)

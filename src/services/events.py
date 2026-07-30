import asyncio
from typing import Callable
from loguru import logger

class EventSystem:
    def __init__(self):
        self._event_handlers = {}

    def on_call(self, event_name: str):
        def decorator(func: Callable):
            if event_name not in self._event_handlers:
                self._event_handlers[event_name] = []
            self._event_handlers[event_name].append(func)
            return func
        return decorator

    async def call(self, event_name: str, *args, **kwargs):
        if event_name in self._event_handlers:
            # run all registered handlers concurrently
            results = await asyncio.gather(
                *(handler(*args, **kwargs) for handler in self._event_handlers[event_name]),
                return_exceptions=True
            )
            # Log any exceptions without crashing other handlers
            for res in results:
                if isinstance(res, Exception):
                    logger.error(f"Exception in event handler '{event_name}': {res}")

events = EventSystem()

# == events ==
RPC_UPDATED = "rpc_updated"

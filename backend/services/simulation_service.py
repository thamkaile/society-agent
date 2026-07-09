import logging

from dynamic_engine.core.engine import DynamicStreamingEngine
from dynamic_engine.config.loader import load_engine_config


logger = logging.getLogger(__name__)


class SimulationService:

    def __init__(self):
        logger.debug("Loading engine...")
        config = load_engine_config()
        self.engine = DynamicStreamingEngine(config)
        logger.debug("Engine ready.")

    async def run_stream(
        self,
        message: str,
        chat_id: str | None = None,
        browser_session_id: str = "",
    ):
        logger.debug("Starting stream...")

        async for event in self.engine.run_project_stream(
            task=message,
            chat_id=chat_id,
            browser_session_id=browser_session_id,
        ):
            logger.debug("Streaming event: %s", event.get("type"))
            yield event

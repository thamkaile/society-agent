from dynamic_engine.core.engine import DynamicStreamingEngine
from dynamic_engine.config.loader import load_engine_config


class SimulationService:

    def __init__(self):
        print("Loading engine...")
        config = load_engine_config()
        self.engine = DynamicStreamingEngine(config)
        print("Engine ready.")

    async def run_stream(self, message: str, chat_id: str | None = None):
        print("Starting stream...")

        async for event in self.engine.run_project_stream(
            task=message,
            chat_id=chat_id,
        ):
            print(event.get("type"))
            yield event
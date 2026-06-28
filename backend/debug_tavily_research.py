"""Run a small Tavily research smoke test without debate agents."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from runtime_bootstrap import bootstrap_runtime, ensure_compatible_python

ensure_compatible_python()
bootstrap_runtime()

try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv(*args, **kwargs):
        return False

from dynamic_engine.config import load_engine_config
from research.tavily_research import TavilyResearch


TASK = "online car parts store in Malaysia"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    load_dotenv(Path(__file__).resolve().parent / ".env")

    config = load_engine_config(Path(__file__).resolve().parent)
    research = TavilyResearch(config.get("research_config", {}).get("tavily", {}))
    result = research.build_structured_evidence(
        TASK,
        "Research competitors, pricing, regulations, customer pain points, and risks.",
        ["Product Manager", "Business Analyst", "Risk & Compliance"],
    )

    print(
        json.dumps(
            {
                "task": TASK,
                "search_queries": result.get("search_queries", []),
                "failed_sources": result.get("failed_sources", []),
                "sources": result.get("sources", []),
                "research_quality": result.get("research_quality"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

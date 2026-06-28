# cli.py
import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from runtime_bootstrap import bootstrap_runtime, ensure_compatible_python

ensure_compatible_python()
bootstrap_runtime()

from dynamic_engine.engine import DynamicStreamingEngine
from dynamic_engine.config import load_engine_config
from dynamic_engine.session_store import SessionStore


def load_config():
    return load_engine_config(Path(__file__).parent)


async def main():
    bootstrap_runtime()
    if os.getenv("DYNAMIC_ENGINE_DEBUG_RESEARCH") == "1":
        logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

    parser = argparse.ArgumentParser(description="Run the dynamic startup planning engine.")
    subparsers = parser.add_subparsers(dest="command")

    new_parser = subparsers.add_parser("new", help="Start a new project session.")
    new_parser.add_argument("task", nargs="*", help="Business idea or product task.")
    new_parser.add_argument("--rounds", type=int, default=3, help="Debate rounds.")
    new_parser.add_argument(
        "--once",
        action="store_true",
        help="Run once without asking for follow-up changes.",
    )

    refine_parser = subparsers.add_parser("refine", help="Refine an existing project session.")
    refine_parser.add_argument("--chat-id", required=True, help="Existing chat_id to resume.")
    refine_parser.add_argument("task", nargs="*", help="Refinement request.")
    refine_parser.add_argument(
        "--once",
        action="store_true",
        help="Run once without asking for follow-up changes.",
    )

    show_parser = subparsers.add_parser("show", help="Show a saved project session.")
    show_parser.add_argument("--chat-id", required=True, help="Existing chat_id to inspect.")

    args = parser.parse_args()

    if args.command == "show":
        show_session(args.chat_id)
        return

    config = load_config()

    if args.command == "new":
        question = " ".join(args.task).strip() or input("\nBusiness idea to simulate: ")
        print(
            "\nProcessing new project "
            "(Root Plan -> PM Questions -> Research -> Planner -> Parallel Debate)...\n"
        )
        chat_id = await run_project_once(config, question, max_rounds=args.rounds)
        if not args.once and chat_id:
            await run_follow_up_loop(config, chat_id)
        print("\nSimulation complete!")
        return
    elif args.command == "refine":
        question = " ".join(args.task).strip() or input("\nRefinement request: ")
        print("\nProcessing refinement (Impact Assessment -> Focused Agents)...\n")
        chat_id = await run_project_once(config, question, chat_id=args.chat_id)
        if not args.once and chat_id:
            await run_follow_up_loop(config, chat_id)
        print("\nSimulation complete!")
        return
    else:
        question = input("\nBusiness idea to simulate: ")
        print(
            "\nProcessing new project "
            "(Root Plan -> PM Questions -> Research -> Planner -> Parallel Debate)...\n"
        )
        chat_id = await run_project_once(config, question, max_rounds=3)
        if chat_id:
            await run_follow_up_loop(config, chat_id)
        print("\nSimulation complete!")
        return


async def run_project_once(
    config: dict,
    question: str,
    chat_id: str | None = None,
    max_rounds: int = 3,
) -> str | None:
    engine = DynamicStreamingEngine(config)
    stream = engine.run_project_stream(question, chat_id=chat_id, max_rounds=max_rounds)
    active_chat_id = chat_id
    async for event in stream:
        event_chat_id = print_event(event)
        active_chat_id = event_chat_id or active_chat_id
    return active_chat_id


async def run_follow_up_loop(config: dict, chat_id: str):
    print(f"\nYou can continue this project with chat_id: {chat_id}")
    while True:
        answer = input("\nDo you want to change anything? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            print(f"\nSession kept at chat_id: {chat_id}")
            return

        request = input("What should change? ").strip()
        if not request:
            print("No change entered, so the session was left as-is.")
            continue

        print("\nProcessing change (PM Impact Assessment -> Research Agent -> Focused Agents)...\n")
        chat_id = await run_project_once(config, request, chat_id=chat_id)


def print_event(event: dict) -> str | None:
    event_type = event.get("type", "unknown")
    agent = event.get("agent", "System")
    content = event.get("content", "")

    if event_type == "session_created":
        print(f"SESSION CREATED: {event.get('chat_id')}")
        print(f"SESSION FILE: {event.get('path')}\n")
        return event.get("chat_id")

    if event_type == "session_loaded":
        print(f"SESSION LOADED: {event.get('chat_id')}")
        print(f"SESSION FILE: {event.get('path')}\n")
        return event.get("chat_id")

    if event_type == "session_saved":
        print(f"SESSION SAVED: {event.get('chat_id')}")
        print(f"SESSION FILE: {event.get('path')}\n")
        return event.get("chat_id")

    if event_type == "impact_assessment":
        print("Impact assessment:")
        print(json.dumps(content, indent=2, ensure_ascii=False))
        print()

    elif event_type == "section_updated":
        print(f"SECTION UPDATED: {event.get('section')}")

    elif event_type == "user_input":
        print(f"\n{'=' * 60}")
        print(f"TASK: {content}")
        print(f"{'=' * 60}\n")

    elif event_type == "phase":
        print(f"\n{'-' * 60}")
        print(content)
        print(f"{'-' * 60}\n")

    elif event_type == "research_complete":
        status = event.get("status")
        if event.get("fallback_used"):
            print(f"Research complete via fallback: {event.get('fallback_reason')}")
        elif status:
            print(f"Research complete! status={status}")
        else:
            print("Research complete!")
        print(f"{content[:500]}...\n")

    elif event_type == "pm_research_plan":
        print("Product Manager research plan ready.")
        print(f"{content[:500]}...\n")

    elif event_type == "orchestration_plan":
        print("Root Coordinator plan ready.")
        print(f"{content[:500]}...\n")

    elif event_type == "agent_selection":
        print(f"AGENT SELECTION: {content}")

    elif event_type == "artifact":
        print(f"ARTIFACT: {content}")

    elif event_type == "research_skipped":
        print(f"Research skipped: {content}\n")

    elif event_type == "agent_response":
        print(f"\n{agent}:")
        print(f"   {content}\n")

    elif event_type == "summarizer":
        print(f"\n{'=' * 60}")
        print("FINAL SUMMARY:")
        print(f"{'=' * 60}")
        print(content)
        print(f"{'=' * 60}\n")

    elif event_type == "error":
        print(f"ERROR [{agent}]: {content}")

    elif event_type == "warning":
        print(f"WARNING [{agent}]: {content}")

    elif event_type == "info":
        print(f"INFO: {content}")

    return None


def show_session(chat_id: str):
    store = SessionStore()
    session = store.load(chat_id)
    path = store.session_dir(chat_id) / "session.json"

    print(f"\nCHAT ID: {session.chat_id}")
    print(f"USER IDEA: {session.user_idea}")
    print(f"SESSION FILE: {path}\n")

    print("SECTIONS")
    print("-" * 60)
    for name, value in session.sections.items():
        content = value.get("content") if isinstance(value, dict) else value
        print(f"\n{name}:")
        print(str(content or value)[:1000])

    if session.decision_log:
        print("\nLATEST DECISION")
        print("-" * 60)
        print(json.dumps(session.decision_log[-1], indent=2, ensure_ascii=False)[:2000])

    if session.change_history:
        print("\nCHANGE HISTORY")
        print("-" * 60)
        for item in session.change_history[-5:]:
            print(json.dumps(item, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())

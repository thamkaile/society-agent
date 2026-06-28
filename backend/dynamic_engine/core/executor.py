# agent_executor.py
import asyncio
import re
from typing import AsyncGenerator, Dict

try:
    from backend.runtime_bootstrap import bootstrap_runtime
except ImportError:
    from runtime_bootstrap import bootstrap_runtime

bootstrap_runtime()

from ..memory import MemoryStore
from ..models import Message


class AgentExecutor:
    """Async executor that handles tool calls with robust error handling."""

    def __init__(self, memory_store: MemoryStore):
        self.memory_store = memory_store

    def _compress_text(self, text: str, max_chars: int = 1200) -> str:
        compact = str(text)
        compact = re.sub(
            r"<longcat_tool_call>.*?</longcat_tool_call>",
            "[tool call removed]",
            compact,
            flags=re.IGNORECASE | re.DOTALL,
        )
        compact = re.sub(
            r"<tool_call>.*?</tool_call>",
            "[tool call removed]",
            compact,
            flags=re.IGNORECASE | re.DOTALL,
        )
        compact = re.sub(
            r"\b(?:snapshot|dom|html|text_content)\s*[:=]\s*.{800,}",
            "[external output compressed]",
            compact,
            flags=re.IGNORECASE | re.DOTALL,
        )
        compact = " ".join(compact.split())
        if len(compact) <= max_chars:
            return compact

        head = compact[: max_chars // 2].rstrip()
        tail = compact[-max_chars // 3 :].lstrip()
        return f"{head} ... [compressed {len(compact)} chars] ... {tail}"

    async def run(
        self,
        agent: object,
        agent_name: str,
        task: str,
    ) -> AsyncGenerator[Dict, None]:
        """
        Yields streaming events (tool_call, tool_result, agent_response) and
        stores the final message in memory.
        """
        agent.reset()
        prompt = task
        max_iterations = 8  # increased for more complex tasks
        consecutive_errors = 0
        max_consecutive_errors = 3

        for iteration in range(max_iterations):
            try:
                # Add timeout to prevent hanging
                response = await asyncio.wait_for(
                    agent.astep(prompt),
                    timeout=60.0  # 60 second timeout per step
                )
                
                if not response or not response.msgs:
                    yield {
                        "type": "warning",
                        "agent": agent_name,
                        "content": f"Empty response received (iteration {iteration + 1})"
                    }
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        break
                    continue

                consecutive_errors = 0  # reset error counter on success
                last_msg = response.msgs[0]

                # Check if it's a function call
                if (last_msg.role_name == "assistant"
                        and hasattr(last_msg, "function_call")
                        and last_msg.function_call is not None):
                    fc = last_msg.function_call
                    tool_name = fc.name
                    args = fc.arguments

                    yield {
                        "type": "tool_call",
                        "agent": agent_name,
                        "tool_name": tool_name,
                        "args": args,
                        "content": f"Calling {tool_name}..."
                    }

                    # Retrieve the tool object from the agent
                    tool = self._find_tool(agent, tool_name)

                    if tool is None:
                        tool_result = f"Tool '{tool_name}' not found or not accessible."
                        compact_error = self._compress_text(tool_result)
                        yield {
                            "type": "tool_error",
                            "agent": agent_name,
                            "content": compact_error
                        }
                    else:
                        try:
                            # Execute tool with timeout
                            tool_result = await asyncio.wait_for(
                                tool.async_call(**args),
                                timeout=30.0  # 30 second timeout for tools
                            )
                        except asyncio.TimeoutError:
                            tool_result = f"Tool '{tool_name}' timed out after 30 seconds"
                            compact_error = self._compress_text(tool_result)
                            yield {
                                "type": "tool_error",
                                "agent": agent_name,
                                "content": compact_error
                            }
                        except Exception as e:
                            tool_result = f"Tool error: {self._compress_text(str(e))}"
                            yield {
                                "type": "tool_error",
                                "agent": agent_name,
                                "content": tool_result
                            }

                    compact_tool_result = self._compress_text(tool_result)

                    yield {
                        "type": "tool_result",
                        "agent": agent_name,
                        "content": compact_tool_result
                    }

                    # Build a function‑response message and continue the loop
                    from camel.messages import BaseMessage

                    function_msg = BaseMessage(
                        role_name="function",
                        content=compact_tool_result,
                        meta_dict={"name": tool_name},
                    )
                    prompt = function_msg
                    
                else:
                    # Final text answer
                    final_text = self._compress_text(last_msg.content or "", 2600)
                    yield {
                        "type": "agent_response",
                        "agent": agent_name,
                        "content": final_text
                    }
                    self.memory_store.add_message(
                        Message(agent=agent_name, content=final_text)
                    )
                    return

            except asyncio.TimeoutError:
                yield {
                    "type": "error",
                    "agent": agent_name,
                    "content": f"Request timed out (iteration {iteration + 1})"
                }
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    break
                    
            except Exception as e:
                yield {
                    "type": "error",
                    "agent": agent_name,
                    "content": f"Unexpected error: {str(e)}"
                }
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    break

        # If loop exhausted, yield a fallback
        fallback = f"(Agent {agent_name} could not complete the task after {max_iterations} attempts)"
        yield {"type": "agent_response", "agent": agent_name, "content": fallback}
        self.memory_store.add_message(Message(agent=agent_name, content=fallback))

    def _find_tool(self, agent: object, tool_name: str):
        """
        Try multiple ways to find a tool in the agent.
        CAMEL versions store tools differently.
        """
        # Method 1: agent.tool_manager._tools dict (newer CAMEL)
        if hasattr(agent, 'tool_manager') and agent.tool_manager:
            if hasattr(agent.tool_manager, '_tools'):
                tool = agent.tool_manager._tools.get(tool_name)
                if tool:
                    return tool

        # Method 2: agent._tools dict (older CAMEL)
        if hasattr(agent, '_tools'):
            tool = agent._tools.get(tool_name)
            if tool:
                return tool

        # Method 3: agent.tools list
        if hasattr(agent, 'tools') and agent.tools:
            for t in agent.tools:
                if hasattr(t, 'name') and t.name == tool_name:
                    return t
                if hasattr(t, 'func') and hasattr(t.func, '__name__') and t.func.__name__ == tool_name:
                    return t

        # Method 4: agent.toolkit (if it's a ChatAgent with toolkit)
        if hasattr(agent, 'toolkit') and agent.toolkit:
            if hasattr(agent.toolkit, 'get_tools'):
                tools = agent.toolkit.get_tools()
                for t in tools:
                    if hasattr(t, 'name') and t.name == tool_name:
                        return t

        return None

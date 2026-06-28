"""Compatibility shim for the renamed executor module."""

from .executor import AgentExecutor

__all__ = ["AgentExecutor"]

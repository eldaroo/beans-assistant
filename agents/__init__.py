"""
Multi-agent system for Beans&Co business management.

This package contains specialized agents for:
- Intent routing and classification
- Read-only analytics queries
- Write operations (business actions)
- Entity resolution and normalization
"""

from .state import AgentState, IntentType, OperationType
from .router import create_router_agent, route_to_next_node
from .read_agent import create_read_agent
from .write_agent import create_write_agent, route_after_write
from .resolver import create_resolver_agent, route_after_resolver

__all__ = [
    "AgentState",
    "IntentType",
    "OperationType",
    "create_router_agent",
    "create_read_agent",
    "create_write_agent",
    "create_resolver_agent",
    "route_to_next_node",
    "route_after_write",
    "route_after_resolver",
]

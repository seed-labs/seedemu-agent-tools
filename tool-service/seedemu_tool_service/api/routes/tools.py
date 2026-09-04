"""Tool discovery and invocation endpoints."""

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from seedemu_tool_service.api.dependencies import get_tool_registry
from seedemu_tool_service.models.tool import ToolInvocationResponse, ToolListResponse
from seedemu_tool_service.registry import ToolRegistry

router = APIRouter(tags=["tools"])


@router.get("", response_model=ToolListResponse)
def list_tools(
    registry: Annotated[ToolRegistry, Depends(get_tool_registry)],
) -> ToolListResponse:
    """List tools currently registered with the service."""

    tools = registry.list_tools()
    return ToolListResponse(tools=tools, count=len(tools))


@router.post("/{name}/invoke", response_model=ToolInvocationResponse)
async def invoke_tool(
    name: str,
    arguments: dict[str, Any],
    registry: Annotated[ToolRegistry, Depends(get_tool_registry)],
) -> ToolInvocationResponse:
    """Invoke a registered tool with the supplied arguments."""

    started = time.perf_counter()
    result = await registry.invoke(name, arguments)
    duration_ms = round((time.perf_counter() - started) * 1000, 3)

    payload = result.model_dump() if isinstance(result, BaseModel) else result
    return ToolInvocationResponse(name=name, result=payload, duration_ms=duration_ms)

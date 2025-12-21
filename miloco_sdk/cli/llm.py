import os
from typing import Any, Dict, List, Tuple

from openai import OpenAI

from miloco_sdk.cli.config import _get_openai_config
from miloco_sdk.cli.mcp_tool import mcp
from miloco_sdk.utils.mcp_jsonrpc import get_tools_openai_format


async def llm_api(messages: List[Dict[str, str]]) -> Tuple[str, List[Dict]]:
    """
    调用 LLM API 并处理流式响应

    Args:
        messages: 消息列表，格式为 [{"role": "user", "content": "..."}]

    Returns:
        Tuple[str, List[Dict]]: (content, tool_calls)

    Raises:
        ValueError: 如果环境变量未设置
    """
    # 延迟检查环境变量，只在函数调用时验证
    api_key, model, base_url = _get_openai_config()

    tools = await get_tools_openai_format(mcp)

    system_prompt = "你是一个高度智能的AI代理，专门负责通过分解任务和调用工具来精确满足用户的请求。你的核心任务是理解用户意图，制定执行计划，并通过与工具的交互，获取足够的信息来生成最终的、准确的答案。"

    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt}] + messages,
        tools=tools,
        stream=True,
        extra_body={"thinking": {"type": "disabled"}},
    )
    content = ""
    tool_calls_dict: Dict[int, Dict[str, Any]] = {}  # 用于存储正在构建的 tool_calls，key 是 tool_call 的 index
    in_reasoning = False  # 跟踪是否正在打印 reasoning_content

    for chunk in response:
        delta = chunk.choices[0].delta
        if hasattr(delta, "reasoning_content") and delta.reasoning_content:
            if not in_reasoning:
                # 开始打印 reasoning_content，添加开始标签
                print("<think>\n", end="", flush=True)
                in_reasoning = True
            reasoning_content = delta.reasoning_content.replace("\n\n", "\n")
            print(reasoning_content, end="", flush=True)
        elif in_reasoning:
            # reasoning_content 结束，添加结束标签并换行
            print("\n</think>", flush=True)
            in_reasoning = False

        if hasattr(delta, "content") and delta.content:
            content += delta.content
            print(delta.content, end="", flush=True)

        if hasattr(delta, "tool_calls") and delta.tool_calls:
            for tool_call_delta in delta.tool_calls:
                # 获取 tool_call 的 index（在流式响应中用作标识符）
                tool_call_index = tool_call_delta.index if hasattr(tool_call_delta, "index") else None
                if tool_call_index is None:
                    continue

                # 初始化或获取现有的 tool_call
                if tool_call_index not in tool_calls_dict:
                    tool_calls_dict[tool_call_index] = {
                        "id": (
                            tool_call_delta.id
                            if hasattr(tool_call_delta, "id") and tool_call_delta.id
                            else f"call_{tool_call_index}"
                        ),
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    }
                else:
                    # 如果后续 chunk 中有 id，更新它
                    if hasattr(tool_call_delta, "id") and tool_call_delta.id:
                        tool_calls_dict[tool_call_index]["id"] = tool_call_delta.id

                # 更新 tool_call 信息
                if hasattr(tool_call_delta, "function") and tool_call_delta.function is not None:
                    if hasattr(tool_call_delta.function, "name") and tool_call_delta.function.name:
                        tool_calls_dict[tool_call_index]["function"]["name"] = tool_call_delta.function.name
                    if hasattr(tool_call_delta.function, "arguments") and tool_call_delta.function.arguments:
                        tool_calls_dict[tool_call_index]["function"]["arguments"] += tool_call_delta.function.arguments

    # 如果流结束时还在 reasoning_content 中，关闭标签
    if in_reasoning:
        print("\n</think>", flush=True)

    # 如果打印了 content，在结束时换行
    if content:
        print("", flush=True)

    # 将 tool_calls_dict 转换为列表
    tool_calls = list(tool_calls_dict.values())

    return content, tool_calls

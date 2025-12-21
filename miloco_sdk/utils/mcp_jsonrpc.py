async def get_tools_openai_format(mcp):

    tools_dict = await mcp.get_tools()
    openai_tools = []
    for tool_name, tool_obj in tools_dict.items():
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_obj.description or "",
                "parameters": tool_obj.parameters or {},
            },
        }
        openai_tools.append(openai_tool)
    return openai_tools


async def get_tools_jsonrpc_format(mcp):
    """
    获取所有工具的 MCP JSON-RPC 格式

    返回 tools/list 方法的响应格式
    """
    # 通过 FastMCP 的 get_tools() 方法获取工具列表
    tools_dict = await mcp.get_tools()

    # 转换为 MCP JSON-RPC 格式
    tools_list = []
    for tool_name, tool_obj in tools_dict.items():
        tool_schema = {
            # "function": tool_obj.run,
            "name": tool_name,
            "description": tool_obj.description or "",
            "inputSchema": tool_obj.parameters or {},
        }
        tools_list.append(tool_schema)

    # 返回 MCP JSON-RPC 格式的响应
    return {"jsonrpc": "2.0", "id": 1, "result": {"tools": tools_list}}


async def call_tool(mcp, tool_name, params):
    """
    调用工具
    """
    tool = await mcp.get_tool(tool_name)
    result = await tool.run(params)
    return result.content[0].text

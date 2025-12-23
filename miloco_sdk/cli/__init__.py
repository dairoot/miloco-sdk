import asyncio
import json
import logging
import re

from miloco_sdk import XiaomiClient
from miloco_sdk.cli.config import IMAGE_PATH, get_openai_config
from miloco_sdk.cli.llm import llm_api
from miloco_sdk.cli.mcp_tool import mcp
from miloco_sdk.cli.utils import get_auth_info
from miloco_sdk.utils.mcp_jsonrpc import call_tool

# 禁用 httpx 模块的日志输出
logging.getLogger("httpx").setLevel(logging.WARNING)


async def on_decode_jpg(did: str, data: bytes, ts: int, channel: int) -> None:
    # 图片存储到本地
    # print("on_decode_jpg: ", IMAGE_PATH)
    with open(IMAGE_PATH, "wb") as f:
        f.write(data)


async def run():
    _ = get_openai_config()
    client = XiaomiClient()
    auth_info = get_auth_info(client)
    client.set_access_token(auth_info["access_token"])
    device_list = client.home.get_device_list()

    online_devices = [line for line in device_list if line.get("isOnline", False)]

    for device in online_devices:
        if "camera" in device["model"]:
            # 检测到摄像头设备，开始拉流
            print(f"检测到摄像头设备: {device['name']}, 正在拉流...")
            await client.miot_camera_stream.run_stream(device["did"], 0, on_decode_jpg_callback=on_decode_jpg)
            # await asyncio.sleep(0.5)

    # await asyncio.sleep(2)
    # tool_result = await call_tool(mcp, "vision_understand", {"question": "看下摄像头"})
    # print("tool_result: ", tool_result)
    # # print("image_base64: ", image_base64)
    # return

    messages = []
    while True:
        question = await asyncio.to_thread(input, "\n请输入问题: ")

        if not question.strip():
            continue

        messages.append({"role": "user", "content": question})
        content, tool_calls = await llm_api(messages)
        messages.append({"role": "assistant", "content": content})

        if tool_calls:
            for tool_call in tool_calls:
                tool_name = tool_call["function"]["name"]
                tool_args = json.loads(tool_call["function"]["arguments"])
                print("tool_call: ", tool_name, tool_args)
                tool_result = await call_tool(mcp, tool_name, tool_args)
                # print("tool_result: ", tool_result)
                messages.append({"role": "tool", "content": tool_result, "tool_call_id": tool_call["id"]})

            content, tool_calls = await llm_api(messages)
            messages.append({"role": "assistant", "content": content})

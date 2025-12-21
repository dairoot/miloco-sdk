import base64
import os

from fastmcp import FastMCP
from openai import OpenAI
from pydantic import Field

from miloco_sdk.cli.config import IMAGE_PATH, _get_openai_config

mcp = FastMCP("Miloco")


# Add an addition tool
@mcp.tool()
async def vision_understand(question: str = Field(description="用户的提问")) -> dict:
    """
    家里摄像头拍摄的图片，理解用户的提问，并给出回答。
    """
    if not os.path.exists(IMAGE_PATH):
        return {"success": False, "error": f"图片文件不存在: {IMAGE_PATH}。请确保摄像头已开始流并接收到图片数据。"}

    image_base64 = None
    with open(IMAGE_PATH, "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode("utf-8")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
            ],
        }
    ]

    api_key, model, base_url = _get_openai_config()
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=False,
        # 关闭思考模式
        extra_body={"thinking": {"type": "disabled"}},
    )
    content = response.choices[0].message.content
    return {"success": True, "content": content}

import base64

from fastmcp import FastMCP
from pydantic import Field

mcp = FastMCP("Miloco")
image_path = "camera.jpg"


# Add an addition tool
@mcp.tool()
async def vision_understand(question: str = Field(description="要理解的问题描述")) -> dict:
    """
    Use this tool to understand the vision of the image.
    """
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    # todo 调用 LLM API 接口，理解图片

    return {"success": True}


if __name__ == "__main__":
    print("需要运行 python examples/stream_to_jpg.py 获取摄像头图片")
    mcp.run(transport="stdio")

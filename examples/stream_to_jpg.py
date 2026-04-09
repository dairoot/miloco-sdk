import asyncio

from miloco_sdk import XiaomiClient
from miloco_sdk.cli.utils import print_device_list

image_path = "camera.jpg"


async def on_decode_jpg(did: str, data: bytes, ts: int, channel: int) -> None:
    # 将数据保存为图片
    with open(image_path, "wb") as f:
        f.write(data)


async def run_camera(did: str):
    client = XiaomiClient()
    client.login()
    # 启动流
    await client.miot_camera_stream.run_stream(did, 0, on_decode_jpg_callback=on_decode_jpg)
    await client.miot_camera_stream.wait_for_data()


async def run():
    client = XiaomiClient()
    client.login()
    device_list = client.home.get_device_list()
    online_devices = [d for d in device_list if d.get("isOnline", False)]

    if not online_devices:
        print("\n设备列表: 暂无在线设备")
        return

    print_device_list(online_devices)
    index = input("请输入摄像头设备序号: ")
    try:
        device_info = online_devices[int(index) - 1]
    except Exception as e:
        print(f"输入错误: {e}")
        return

    await run_camera(device_info["did"])


# Start the server
if __name__ == "__main__":
    asyncio.run(run())

    # mcp.run(transport="stdio")

import asyncio

import numpy as np
import sounddevice as sd

from miloco_sdk import XiaomiClient
from miloco_sdk.cli.utils import get_auth_info, print_device_list

audio_stream = sd.OutputStream(samplerate=16000, channels=1, dtype=np.int16)
audio_stream.start()


async def on_decode_pcm(did: str, data: bytes, ts: int, channel: int) -> None:
    """接收解码后的 PCM 音频数据并播放"""
    # 将字节数据转换为 numpy 数组并播放
    audio_array = np.frombuffer(data, dtype=np.int16)
    audio_stream.write(audio_array)


async def run():

    client = XiaomiClient()
    auth_info = get_auth_info(client)
    client.set_access_token(auth_info["access_token"])

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

    # 启动流，使用 on_decode_pcm_callback 接收解码后的 PCM 数据
    await client.miot_camera_stream.run_stream(device_info["did"], 0, on_decode_pcm_callback=on_decode_pcm)
    await client.miot_camera_stream.wait_for_data()


if __name__ == "__main__":
    asyncio.run(run())

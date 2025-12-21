import asyncio
import json
import logging
import os
import sys
import uuid as uuid_lib
from re import A

cur_path = os.path.abspath(__file__)
parent = os.path.dirname
# 确保当前项目的根目录优先于其他同名的 `src` 包（例如其它项目中的 `src`）
sys.path.insert(0, parent(parent(cur_path)))

from miloco_sdk import XiaomiClient

access_token = os.getenv("ACCESS_TOKEN")

if not access_token:
    raise ValueError("ACCESS_TOKEN is not set")


async def on_decode_jpg(did: str, data: bytes, ts: int, channel: int) -> None:
    print(f"on_decode_jpg: {did}, {len(data)}, {ts}, {channel}")


async def on_raw_video(did: str, data: bytes, ts: int, seq: int, channel: int) -> None:
    print(f"on_raw_video: {did}, {len(data)}, {ts}, {seq}, {channel}")


async def on_raw_audio(did: str, data: bytes, ts: int, seq: int, channel: int) -> None:
    # 这是编码后的原始音频数据（可能是 OPUS、G711A 或 G711U 格式）
    # 从数据特征来看，很可能是 OPUS 格式
    print(f"on_raw_audio (编码格式，可能是 OPUS): {did}, {len(data)} bytes, {ts}, {seq}, {channel}")
    # print(data)  # 原始编码数据，通常是 OPUS 格式


async def on_decode_pcm(did: str, data: bytes, ts: int, channel: int) -> None:
    # 这是解码后的 PCM 音频数据（16-bit, mono, 16kHz）
    print(f"on_decode_pcm (PCM 格式): {did}, {len(data)} bytes, {ts}, {channel}")


class TestCameraStream(object):

    async def run(self):
        client = XiaomiClient(access_token=access_token)
        await client.miot_camera_stream.run_stream(
            "1177002050",
            0,
            on_raw_video_callback=on_raw_video,
            on_decode_jpg_callback=on_decode_jpg,
            on_raw_audio_callback=on_raw_audio,
            on_decode_pcm_callback=on_decode_pcm,
        )

        await client.miot_camera_stream.wait_for_data()


if __name__ == "__main__":
    asyncio.run(TestCameraStream().run())

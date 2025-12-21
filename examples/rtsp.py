import asyncio
from asyncio.subprocess import PIPE, create_subprocess_exec

from miloco_sdk import XiaomiClient
from miloco_sdk.cli.utils import get_auth_info, print_device_list

# RTSP 服务器地址
RTSP_URL = "rtsp://127.0.0.1:8554/live"

"""
使用说明：
1. 需要先启动 RTSP 服务器，推荐使用 mediamtx：
    - 下载：https://github.com/bluenviron/mediamtx/releases
    - 运行：./mediamtx mediamtx.yml
    - 配置文件：
    ```mediamtx.yml
    rtspAddress: :8554
    paths:
    live:
        source: publisher
    ```
2. 运行此脚本，推流命令
- python examples/rtsp.py

3. 然后接收命令
- ffplay -fflags nobuffer -flags low_delay -framedrop rtsp://127.0.0.1:8554/live
"""


def detect_keyframe_and_codec(data: bytes) -> tuple[bool, str]:
    """检测关键帧和 codec 类型，返回 (is_keyframe, codec)"""
    i = 0
    while i < len(data) - 5:
        # 查找 NAL 起始码
        if data[i : i + 3] == b"\x00\x00\x01":
            header = data[i + 3]
            i += 3
        elif data[i : i + 4] == b"\x00\x00\x00\x01":
            header = data[i + 4]
            i += 4
        else:
            i += 1
            continue

        h264_type = header & 0x1F
        h265_type = (header >> 1) & 0x3F

        # H265: VPS=32, SPS=33, PPS=34, IDR=19/20
        if h265_type in (19, 20, 32, 33, 34):
            return True, "hevc"
        # H264: SPS=7, PPS=8, IDR=5
        if h264_type in (5, 7, 8):
            return True, "h264"
    return False, "unknown"


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

    # 推流状态
    ffmpeg_proc = None
    codec = None
    frame_count = 0

    async def on_raw_video(did: str, data: bytes, ts: int, seq: int, channel: int):
        nonlocal ffmpeg_proc, codec, frame_count
        frame_count += 1

        # 等待关键帧并检测 codec
        if ffmpeg_proc is None:
            is_keyframe, detected = detect_keyframe_and_codec(data)
            if not is_keyframe or detected == "unknown":
                if frame_count % 50 == 0:
                    print(f"等待关键帧... 第 {frame_count} 帧")
                return

            codec = detected
            print(f"检测到 codec: {codec}，启动推流...")
            ffmpeg_proc = await create_subprocess_exec(
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-probesize",
                "32",
                "-analyzeduration",
                "0",
                "-fflags",
                "+genpts+nobuffer+discardcorrupt",
                "-flags",
                "low_delay",
                "-f",
                codec,
                "-i",
                "pipe:0",
                "-c:v",
                "copy",
                "-an",
                "-flush_packets",
                "1",
                "-f",
                "rtsp",
                "-rtsp_transport",
                "tcp",
                RTSP_URL,
                stdin=PIPE,
            )

        # 写入 ffmpeg（不等待 drain 以降低延迟）
        if ffmpeg_proc.stdin and not ffmpeg_proc.stdin.is_closing():
            try:
                ffmpeg_proc.stdin.write(data)
                if frame_count % 100 == 0:
                    print(f"推流中... 第 {frame_count} 帧, len={len(data)}")
            except Exception as e:
                print(f"写入错误: {e}")

    print(f"\n准备推流到: {RTSP_URL}")

    try:
        await client.miot_camera_stream.run_stream(device_info["did"], 0, on_raw_video_callback=on_raw_video)
        await client.miot_camera_stream.wait_for_data()
    except Exception as e:
        print(f"推流失败，请检查设备与当前程序在同一局域网: {e}")
        return


if __name__ == "__main__":
    asyncio.run(run())

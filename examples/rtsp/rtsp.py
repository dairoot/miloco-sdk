import argparse
import asyncio
import logging
import os
import subprocess
import tempfile
from asyncio.subprocess import PIPE, create_subprocess_exec

logger = logging.getLogger(__name__)

FFMPEG_MIN_VERSION = "8.0.1"


def check_ffmpeg_version():
    import re

    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        first_line = result.stdout.split("\n")[0]
        # 匹配版本号，如 "7.1.1", "n8.0.1", "N-xxxxx-g..."
        match = re.search(r"version\s+[nN]?(\d+\.\d+(?:\.\d+)?)", first_line)
        if match:
            version_str = match.group(1)
            current = tuple(int(x) for x in version_str.split("."))
            required = tuple(int(x) for x in FFMPEG_MIN_VERSION.split("."))
            if current < required:
                logger.warning("ffmpeg 版本 %s 低于推荐版本 %s，可能导致推流异常", version_str, FFMPEG_MIN_VERSION)
            else:
                logger.info("ffmpeg 版本: %s", version_str)
        else:
            logger.info("ffmpeg 版本信息: %s", first_line)
    except FileNotFoundError:
        logger.error("未找到 ffmpeg，请先安装 ffmpeg >= %s", FFMPEG_MIN_VERSION)


check_ffmpeg_version()

from miloco_sdk import XiaomiClient
from miloco_sdk.cli.utils import get_auth_info, print_device_list
from miloco_sdk.utils.types import MIoTCameraStatus, MIoTCameraVideoQuality

logging.getLogger("miloco_sdk.plugin.miot.camera").setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# RTSP 服务器地址（Docker 环境使用 go2rtc 容器名，本地使用 127.0.0.1）
RTSP_HOST = os.getenv("RTSP_HOST", "127.0.0.1")
RTSP_URL = f"rtsp://{RTSP_HOST}:8554/live"


def parse_nals(data: bytes) -> list[tuple[int, bytes]]:
    """解析数据中的所有 NAL 单元，返回 [(start_offset, nal_bytes), ...]"""
    nals = []
    offsets = []
    i = 0
    while i < len(data) - 3:
        if data[i : i + 4] == b"\x00\x00\x00\x01":
            offsets.append(i)
            i += 4
        elif data[i : i + 3] == b"\x00\x00\x01":
            offsets.append(i)
            i += 3
        else:
            i += 1
    for idx, off in enumerate(offsets):
        end = offsets[idx + 1] if idx + 1 < len(offsets) else len(data)
        nals.append((off, data[off:end]))
    return nals


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


async def run(enable_audio: bool = False):
    client = XiaomiClient()
    auth_info = get_auth_info(client)
    client.set_access_token(auth_info["access_token"])

    device_list = client.home.get_device_list()
    online_devices = [d for d in device_list if d.get("isOnline", False)]


    camera_devices = [ d for d in online_devices if "camera" in d["model"] ]

    if not camera_devices:
        logger.warning("设备列表: 暂无摄像头设备")
        return


    if len(camera_devices) == 1:
        device_info = camera_devices[0]
        logger.info("检测到摄像头设备: %s, 正在拉流...", device_info['name'])

    else:
        print_device_list(camera_devices)
        env_did = os.getenv("DEVICE_DID")
        if env_did:
            logger.info("使用环境变量 DEVICE_DID=%s", env_did)
            device_info = next((d for d in online_devices if d.get("did") == env_did), None)
            if not device_info:
                logger.error("未找到 did 为 %s 的在线设备", env_did)
                return
        else:
            index = input("请输入摄像头设备序号: ")
            try:
                device_info = online_devices[int(index) - 1]
            except Exception as e:
                logger.error("输入错误: %s", e)
                return

        logger.info("选中的设备: %s", device_info.get("name"))

    # 校验摄像头是否在线
    status = await client.miot_camera_status.get_status_async(device_info)
    if status != MIoTCameraStatus.CONNECTED:
        logger.error("摄像头不在线，请检查摄像头跟脚本是否在同一局域网")
        return

    # 音频相关状态
    audio_fifo = None
    audio_file = None
    fifo_ready = asyncio.Event()
    audio_frame_count = 0

    if enable_audio:
        audio_fifo = os.path.join(tempfile.gettempdir(), "camera_audio.fifo")
        try:
            os.unlink(audio_fifo)
        except FileNotFoundError:
            pass
        os.mkfifo(audio_fifo)

    async def open_audio_fifo():
        """后台任务：打开音频 FIFO 写端"""
        nonlocal audio_file
        loop = asyncio.get_event_loop()
        audio_file = await loop.run_in_executor(None, lambda: open(audio_fifo, "wb", buffering=0))
        fifo_ready.set()
        logger.info("音频管道已连接")

    async def on_decode_pcm(did: str, data: bytes, ts: int, channel: int):
        """接收解码后的 PCM 音频数据"""
        nonlocal audio_frame_count
        audio_frame_count += 1

        if not fifo_ready.is_set():
            return

        if audio_file:
            try:
                audio_file.write(data)
                if audio_frame_count % 200 == 0:
                    logger.debug("音频推流中... 第 %d 帧", audio_frame_count)
            except BrokenPipeError:
                pass
            except Exception as e:
                logger.error("音频错误: %s", e)

    # 推流状态
    ffmpeg_proc = None
    codec = None
    frame_count = 0
    stream_stopped = asyncio.Event()

    async def monitor_ffmpeg():
        """监控 ffmpeg 进程，退出时通知主循环"""
        ret = await ffmpeg_proc.wait()
        logger.error("ffmpeg 进程已退出 (code=%s)", ret)
        stream_stopped.set()
    # 缓存 VPS/SPS/PPS，确保每个 IDR 帧前都携带参数集
    cached_parameter_sets: dict[str, bytes] = {}  # h265: VPS/SPS/PPS, h264: SPS/PPS

    def inject_parameter_sets(data: bytes, codec_type: str) -> bytes:
        """在 IDR 帧前注入缓存的 VPS/SPS/PPS 参数集，确保中途接入的客户端能解码"""
        nals = parse_nals(data)
        if not nals:
            return data

        has_idr = False
        has_params = False

        if codec_type == "hevc":
            param_types = {32, 33, 34}  # VPS, SPS, PPS
            idr_types = {19, 20}
            for _, nal_data in nals:
                # 跳过起始码获取 NAL header
                if nal_data[:4] == b"\x00\x00\x00\x01":
                    header = nal_data[4]
                elif nal_data[:3] == b"\x00\x00\x01":
                    header = nal_data[3]
                else:
                    continue
                nal_type = (header >> 1) & 0x3F
                if nal_type in idr_types:
                    has_idr = True
                if nal_type in param_types:
                    has_params = True
                    # 更新缓存
                    cached_parameter_sets[f"h265_{nal_type}"] = nal_data
        else:  # h264
            param_types = {7, 8}  # SPS, PPS
            idr_types = {5}
            for _, nal_data in nals:
                if nal_data[:4] == b"\x00\x00\x00\x01":
                    header = nal_data[4]
                elif nal_data[:3] == b"\x00\x00\x01":
                    header = nal_data[3]
                else:
                    continue
                nal_type = header & 0x1F
                if nal_type in idr_types:
                    has_idr = True
                if nal_type in param_types:
                    has_params = True
                    cached_parameter_sets[f"h264_{nal_type}"] = nal_data

        # IDR 帧但缺少参数集 -> 注入缓存的参数集
        if has_idr and not has_params and cached_parameter_sets:
            if codec_type == "hevc":
                prefix = b""
                for t in (32, 33, 34):  # VPS -> SPS -> PPS 顺序
                    key = f"h265_{t}"
                    if key in cached_parameter_sets:
                        prefix += cached_parameter_sets[key]
                if prefix:
                    return prefix + data
            else:
                prefix = b""
                for t in (7, 8):  # SPS -> PPS 顺序
                    key = f"h264_{t}"
                    if key in cached_parameter_sets:
                        prefix += cached_parameter_sets[key]
                if prefix:
                    return prefix + data

        return data

    async def on_raw_video(did: str, data: bytes, ts: int, seq: int, channel: int):
        nonlocal ffmpeg_proc, codec, frame_count
        frame_count += 1

        # 等待关键帧并检测 codec
        if ffmpeg_proc is None:
            is_keyframe, detected = detect_keyframe_and_codec(data)
            if not is_keyframe or detected == "unknown":
                if frame_count % 50 == 0:
                    logger.debug("等待关键帧... 第 %d 帧", frame_count)
                return

            codec = detected
            logger.info("检测到 codec: %s，启动推流...", codec)

            if enable_audio:
                asyncio.create_task(open_audio_fifo())
                ffmpeg_proc = await create_subprocess_exec(
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "info",
                    # 视频输入 - 使用系统时钟作为时间戳
                    "-use_wallclock_as_timestamps",
                    "1",
                    "-thread_queue_size",
                    "512",
                    "-fflags",
                    "+genpts",
                    "-f",
                    codec,
                    "-i",
                    "pipe:0",
                    # 音频输入 - 同样使用系统时钟
                    "-use_wallclock_as_timestamps",
                    "1",
                    "-thread_queue_size",
                    "512",
                    "-f",
                    "s16le",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "-i",
                    audio_fifo,
                    # 映射
                    "-map",
                    "0:v",
                    "-map",
                    "1:a",
                    # 编码
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-ar",
                    "16000",
                    # 音频时间戳修复
                    "-af",
                    "aresample=async=1:first_pts=0",
                    # 输出
                    "-f",
                    "rtsp",
                    "-rtsp_transport",
                    "tcp",
                    RTSP_URL,
                    stdin=PIPE,
                )
            else:
                ffmpeg_proc = await create_subprocess_exec(
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "info",
                    "-fflags",
                    "+genpts+discardcorrupt",
                    "-f",
                    codec,
                    "-i",
                    "pipe:0",
                    "-c:v",
                    "copy",
                    "-bsf:v",
                    "extract_extradata",
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

            asyncio.create_task(monitor_ffmpeg())

        # 检测 ffmpeg 是否已退出
        if stream_stopped.is_set():
            return

        # 注入参数集并写入 ffmpeg
        data = inject_parameter_sets(data, codec)
        if ffmpeg_proc.stdin and not ffmpeg_proc.stdin.is_closing():
            try:
                ffmpeg_proc.stdin.write(data)
                if frame_count % 100 == 0:
                    if enable_audio:
                        logger.debug("视频推流中... 第 %d 帧, 音频 %d 帧", frame_count, audio_frame_count)
                    else:
                        logger.debug("推流中... 第 %d 帧, len=%d", frame_count, len(data))
            except (BrokenPipeError, ConnectionResetError):
                logger.error("ffmpeg 管道断开，推流中断")
                stream_stopped.set()
            except Exception as e:
                logger.error("写入错误: %s", e)

    mode = "视频 + 音频" if enable_audio else "仅视频"
    logger.info("准备推流到: %s（%s）", RTSP_URL, mode)

    try:
        stream_kwargs = {
            "on_raw_video_callback": on_raw_video,
            "video_quality": MIoTCameraVideoQuality.HIGH,
        }
        if enable_audio:
            stream_kwargs["on_decode_pcm_callback"] = on_decode_pcm

        await client.miot_camera_stream.run_stream(device_info["did"], 0, **stream_kwargs)

        logger.info("开始接收摄像头数据，按 Ctrl+C 结束...")
        # 等待推流中断信号或用户中断
        while not stream_stopped.is_set():
            await asyncio.sleep(1)

        if stream_stopped.is_set():
            logger.info("推流已停止，正在退出...")
    except KeyboardInterrupt:
        logger.info("收到退出信号...")
    except Exception as e:
        logger.error("推流失败，请检查设备与当前程序在同一局域网: %s", e)
    finally:
        await client.miot_camera_stream.cleanup()
        if enable_audio:
            if audio_file:
                try:
                    audio_file.close()
                except Exception:
                    pass
            if audio_fifo:
                try:
                    os.unlink(audio_fifo)
                except Exception:
                    pass
        if ffmpeg_proc:
            try:
                if ffmpeg_proc.stdin:
                    ffmpeg_proc.stdin.close()
                ffmpeg_proc.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="摄像头 RTSP 推流")
    parser.add_argument("--audio", action="store_true", help="启用音频推流")
    args = parser.parse_args()
    asyncio.run(run(enable_audio=args.audio))

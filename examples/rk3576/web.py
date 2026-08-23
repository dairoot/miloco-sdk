import asyncio
import io
import os
import sys
import threading
from queue import Queue
from threading import Lock

import cv2
import numpy as np
from aiohttp import web
from av.packet import Packet
from av.video.codeccontext import VideoCodecContext

from miloco_sdk import XiaomiClient
from miloco_sdk.cli.utils import print_device_list
from miloco_sdk.utils.types import MIoTCameraVideoQuality

# 全局变量用于视频解码和显示
video_decoder = None
detect_and_draw = None  # yolo 模式下为检测函数：吃 BGR 帧，返回画好框的 BGR 帧
# 用于存储视频帧的队列
frame_queue = Queue(maxsize=2)
frame_lock = Lock()
latest_frame = None

# Rockchip VPU 硬解输出尺寸（VPU 内部用 RGA 缩放），设成 0 表示保持摄像头原始分辨率
HW_WIDTH, HW_HEIGHT = 1920, 1080
# yolo 模式下 JPEG 得 CPU 软编，1080p 要 24ms 而 720p 只要 11ms，所以降一档
YOLO_WIDTH, YOLO_HEIGHT = 1280, 720
Gst = None
gst_pipeline = None
gst_appsrc = None  # 为 None 时表示没有硬解，回退到 PyAV 软解

# 解码线程和检测线程之间的单槽，只保留最新一帧
pending_cond = threading.Condition()
pending_frame = None

# HTML 页面模板
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>小米摄像头 - HEVC 视频流</title>
    <style>
        html, body {
            margin: 0;
            padding: 0;
            height: 100vh;
            width: 100vw;
            overflow: hidden;
            background-color: #1a1a1a;
            color: #fff;
            font-family: Arial, sans-serif;
            display: flex;
            flex-direction: column;
        }
        h1 {
            text-align: center;
            margin: 10px 0;
            padding: 0 20px;
            flex-shrink: 0;
            font-size: 1.5em;
        }
        #video-container {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            background-color: #000;
            padding: 10px;
            margin: 0 10px 10px 10px;
            border-radius: 8px;
            min-height: 0;
            overflow: hidden;
        }
        img {
            max-width: 100%;
            max-height: 100%;
            width: auto;
            height: auto;
            object-fit: contain;
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <h1>小米摄像头 - HEVC 视频流 (YOLO 检测)</h1>
    <div id="video-container">
        <img id="video-stream" src="/video_feed" alt="视频流">
    </div>
    <script>
        // MJPEG 流处理
        const img = document.getElementById('video-stream');
        let reconnectTimeout;

        img.onerror = function() {
            console.log('视频流加载错误，尝试重新连接...');
            clearTimeout(reconnectTimeout);
            reconnectTimeout = setTimeout(() => {
                img.src = '/video_feed?t=' + new Date().getTime();
            }, 2000);
        };

        img.onload = function() {
            clearTimeout(reconnectTimeout);
        };

        // 初始加载
        img.src = '/video_feed?t=' + new Date().getTime();
    </script>
</body>
</html>
"""


def on_hw_sample(sink):
    """GStreamer 推流线程回调：必须尽快返回，卡在这里会反压到 appsrc，延迟一路堆积。"""
    global latest_frame, pending_frame

    sample = sink.emit("pull-sample")
    if sample is None:
        return Gst.FlowReturn.OK

    buffer = sample.get_buffer()
    ok, info = buffer.map(Gst.MapFlags.READ)
    if not ok:
        return Gst.FlowReturn.OK
    try:
        if detect_and_draw:
            # YOLO 分支：只把 NV12 裸帧丢进单槽，检测和 JPEG 编码交给 detect_worker
            caps = sample.get_caps().get_structure(0)
            item = (caps.get_value("width"), caps.get_value("height"), bytes(info.data))
            with pending_cond:
                # 覆盖上一帧：处理不过来时丢的是旧帧，延迟不会累积
                pending_frame = item
                pending_cond.notify()
        else:
            # VPU 已经编好 JPEG，直接用
            with frame_lock:
                latest_frame = bytes(info.data)
    finally:
        buffer.unmap(info)
    return Gst.FlowReturn.OK


def detect_worker():
    """独立线程跑 YOLO + JPEG 编码，永远只处理单槽里最新的那一帧。"""
    global latest_frame, pending_frame

    while True:
        with pending_cond:
            while pending_frame is None:
                pending_cond.wait()
            width, height, data = pending_frame
            pending_frame = None

        try:
            nv12 = np.frombuffer(data, dtype=np.uint8).reshape(height * 3 // 2, width)
            bgr_frame = detect_and_draw(cv2.cvtColor(nv12, cv2.COLOR_YUV2BGR_NV12))
            _, buf = cv2.imencode(".jpg", bgr_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        except Exception as e:
            # 单帧出错不能让整个线程退出，否则画面会永久卡住
            print(f"检测线程出错: {e}")
            continue

        with frame_lock:
            latest_frame = buf.tobytes()


def init_hw_decoder():
    """尝试启动 Rockchip VPU 硬解流水线，不可用时返回 None。"""
    global Gst, gst_pipeline

    try:
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst as _Gst
    except (ImportError, ValueError):
        return None

    Gst = _Gst
    Gst.init(None)
    if Gst.ElementFactory.make("mppvideodec") is None:
        return None

    # 有 YOLO 时要拿裸帧做检测，否则让 VPU 顺手把 JPEG 也编好
    tail = "video/x-raw,format=NV12" if detect_and_draw else "mppjpegenc q-factor=80"
    width, height = (YOLO_WIDTH, YOLO_HEIGHT) if detect_and_draw else (HW_WIDTH, HW_HEIGHT)
    gst_pipeline = Gst.parse_launch(
        "appsrc name=src is-live=true do-timestamp=true format=time "
        'caps="video/x-h265,stream-format=byte-stream,alignment=au,parsed=true" '
        f"! mppvideodec width={width} height={height} ! {tail} "
        "! appsink name=sink sync=false max-buffers=2 drop=true"
    )
    sink = gst_pipeline.get_by_name("sink")
    sink.set_property("emit-signals", True)
    sink.connect("new-sample", on_hw_sample)
    if detect_and_draw:
        threading.Thread(target=detect_worker, daemon=True).start()
    gst_pipeline.set_state(Gst.State.PLAYING)
    print(f"已启用 Rockchip VPU 硬解，输出 {width}x{height}")
    return gst_pipeline.get_by_name("src")


async def on_raw_video(did: str, data: bytes, ts: int, seq: int, channel: int):
    global video_decoder, latest_frame

    if gst_appsrc is not None:
        # 硬解：只把码流丢给 VPU，事件循环不做任何解码工作
        gst_appsrc.emit("push-buffer", Gst.Buffer.new_wrapped(data))
        return

    # 首次调用时创建 HEVC 解码器
    if video_decoder is None:
        video_decoder = VideoCodecContext.create("hevc", "r")
        print("已创建 HEVC 视频解码器")

    # 解码视频帧
    pkt = Packet(data)
    frames = video_decoder.decode(pkt)

    for frame in frames:
        # 转换为 BGR 格式 (OpenCV 使用 BGR)
        bgr_frame = frame.to_ndarray(format="bgr24")

        if detect_and_draw:
            bgr_frame = detect_and_draw(bgr_frame)

        # 将帧编码为 JPEG
        _, buffer = cv2.imencode(".jpg", bgr_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

        # 更新最新帧
        with frame_lock:
            latest_frame = buffer.tobytes()


async def index_handler(request):
    """返回 HTML 页面"""
    return web.Response(text=HTML_PAGE, content_type="text/html")


async def video_feed_handler(request):
    """MJPEG 视频流处理"""
    response = web.StreamResponse()
    response.headers["Content-Type"] = "multipart/x-mixed-replace; boundary=frame"
    await response.prepare(request)

    last_sent = None
    try:
        while True:
            # 检查客户端是否已断开连接
            if request.transport is None or request.transport.is_closing():
                break

            try:
                # 获取最新帧
                with frame_lock:
                    frame_data = latest_frame

                # 帧没更新就不重复发，1080p 下能省一半带宽
                if frame_data is not None and frame_data is not last_sent:
                    last_sent = frame_data
                    # 发送 MJPEG 帧
                    boundary = b"--frame\r\n"
                    content_type = b"Content-Type: image/jpeg\r\n\r\n"
                    await response.write(boundary + content_type + frame_data + b"\r\n")

                # 控制帧率，避免过快
                await asyncio.sleep(0.033)  # 约 30 FPS
            except (ConnectionResetError, ConnectionAbortedError, asyncio.CancelledError) as e:
                # 客户端断开连接，正常退出
                break
            except Exception as e:
                # 其他错误，记录但不中断
                if "closing transport" not in str(e).lower():
                    print(f"视频流错误: {e}")
                break
    except asyncio.CancelledError:
        # 任务被取消，正常退出
        pass
    except Exception as e:
        if "closing transport" not in str(e).lower():
            print(f"视频流处理错误: {e}")
    finally:
        try:
            if not response._closed:
                await response.write_eof()
        except Exception:
            pass

    return response


async def run():
    client = XiaomiClient()
    client.login()
    device_list = client.home.get_device_list()
    online_devices = [d for d in device_list if d.get("isOnline", False)]

    if not online_devices:
        print("\n设备列表: 暂无在线设备")
        return

    print_device_list(online_devices)
    env_did = os.getenv("DEVICE_DID")
    if env_did:
        print(f"使用环境变量 DEVICE_DID={env_did}")
        device_info = next((d for d in online_devices if d.get("did") == env_did), None)
        if not device_info:
            print(f"未找到 did 为 {env_did} 的在线设备")
            return
    else:
        index = input("请输入摄像头设备序号: ")
        try:
            device_info = online_devices[int(index) - 1]
        except Exception as e:
            print(f"输入错误: {e}")
            return

    global gst_appsrc
    gst_appsrc = init_hw_decoder()
    if gst_appsrc is None:
        print("未检测到 Rockchip VPU（mppvideodec），回退到 CPU 软解，高分辨率下可能卡顿")

    # 创建 web 应用
    app = web.Application()
    app.router.add_get("/", index_handler)
    app.router.add_get("/video_feed", video_feed_handler)

    # 启动 web 服务器
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8180)
    await site.start()

    print("\nWeb 服务器已启动: http://localhost:8180")
    print("请在浏览器中打开上述地址查看视频流")

    # 启动视频流
    stream_task = asyncio.create_task(
        client.miot_camera_stream.run_stream(
            device_info["did"], 0, on_raw_video_callback=on_raw_video, video_quality=MIoTCameraVideoQuality.LOW
        )
    )

    try:
        # 等待流数据
        await client.miot_camera_stream.wait_for_data()
    except KeyboardInterrupt:
        print("\n正在关闭...")
    finally:
        stream_task.cancel()
        if gst_pipeline is not None:
            gst_pipeline.set_state(Gst.State.NULL)
        await runner.cleanup()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "yolo":
        # 这块板子是 ARMv8.0，PyPI 的 torch aarch64 wheel 一跑卷积就 SIGILL，优先走 NPU
        try:
            from rknn_yolo import RknnYolo

            detect_and_draw = RknnYolo().detect_and_draw
            print("YOLO 跑在 RK3576 NPU 上")
        except (ImportError, RuntimeError) as e:
            from ultralytics import YOLO

            _yolo = YOLO("yolo11n.pt")

            def detect_and_draw(frame):
                return _yolo(frame, verbose=False)[0].plot()

            print(f"NPU 不可用（{e}），YOLO 回退到 ultralytics")
    asyncio.run(run())

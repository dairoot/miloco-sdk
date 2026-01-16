import asyncio
import io
from queue import Queue
from threading import Lock
import sys
import cv2
from aiohttp import web
from av.packet import Packet
from av.video.codeccontext import VideoCodecContext

from miloco_sdk import XiaomiClient
from miloco_sdk.cli.utils import get_auth_info, print_device_list
from miloco_sdk.utils.types import MIoTCameraVideoQuality

# 全局变量用于视频解码和显示
video_decoder = None
model = None
# 用于存储视频帧的队列
frame_queue = Queue(maxsize=2)
frame_lock = Lock()
latest_frame = None

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


async def on_raw_video(did: str, data: bytes, ts: int, seq: int, channel: int):
    global video_decoder, latest_frame

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

        if model:
            # 进行检测
            results = model(bgr_frame, verbose=False)

            # 绘制结果
            bgr_frame = results[0].plot()

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

    try:
        while True:
            # 检查客户端是否已断开连接
            if request.transport is None or request.transport.is_closing():
                break

            try:
                # 获取最新帧
                with frame_lock:
                    frame_data = latest_frame

                if frame_data:
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

    # 创建 web 应用
    app = web.Application()
    app.router.add_get("/", index_handler)
    app.router.add_get("/video_feed", video_feed_handler)

    # 启动 web 服务器
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

    print("\nWeb 服务器已启动: http://localhost:8080")
    print("请在浏览器中打开上述地址查看视频流")

    # 启动视频流
    stream_task = asyncio.create_task(
        client.miot_camera_stream.run_stream(
            device_info["did"], 0, on_raw_video_callback=on_raw_video, video_quality=MIoTCameraVideoQuality.HIGH
        )
    )

    try:
        # 等待流数据
        await client.miot_camera_stream.wait_for_data()
    except KeyboardInterrupt:
        print("\n正在关闭...")
    finally:
        stream_task.cancel()
        await runner.cleanup()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "yolo":
        from ultralytics import YOLO
        model = YOLO("yolo11n.pt")
    asyncio.run(run())


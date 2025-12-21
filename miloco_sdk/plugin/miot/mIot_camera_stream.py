import asyncio

from miloco_sdk.base import BaseApi
from miloco_sdk.plugin.miot.client import MIoTClient
from miloco_sdk.utils.const import MICO_REDIRECT_URI
from miloco_sdk.utils.types import MIoTCameraVideoQuality, MIoTOauthInfo


class MIoTCameraStream(BaseApi):

    async def run_stream(
        self,
        did: str,
        channel: int,
        on_raw_video_callback=None,
        on_decode_jpg_callback=None,
        on_raw_audio_callback=None,
        on_decode_pcm_callback=None,
        video_quality=MIoTCameraVideoQuality.LOW # 清晰度， 默认 LOW，可改成 HIGH
    ) -> None:
        """从小米云端获取并打印摄像头原始视频流信息。"""
        # 解析 oauth_info
        oauth_dict = {"access_token": self._client._access_token, "refresh_token": "", "expires_ts": 0}
        oauth_info = MIoTOauthInfo(**oauth_dict)

        # 初始化 MIoTClient
        self.miot_client = MIoTClient(
            uuid=self._client._device_id,
            redirect_uri=MICO_REDIRECT_URI,
            lang="zh_CN",
            oauth_info=oauth_info,
        )
        await self.miot_client.init_async()

        # 获取摄像头列表，并找到我们的 did
        cameras = await self.miot_client.get_cameras_async()
        camera_info = cameras[did]

        # 创建摄像头实例
        self.camera_instance = await self.miot_client.create_camera_instance_async(
            camera_info=camera_info,
            frame_interval=500,  # 毫秒，内部解码用
            enable_hw_accel=False,  # 关闭硬件加速，脚本调试更稳定
        )

        if on_raw_video_callback:
            await self.camera_instance.register_raw_video_async(
                callback=on_raw_video_callback,
                channel=channel,
                multi_reg=False,
            )

        if on_decode_jpg_callback:
            await self.camera_instance.register_decode_jpg_async(
                callback=on_decode_jpg_callback,
                channel=channel,
                multi_reg=False,
            )

        if on_raw_audio_callback:
            await self.camera_instance.register_raw_audio_async(
                callback=on_raw_audio_callback,
                channel=channel,
                multi_reg=False,
            )

        if on_decode_pcm_callback:
            await self.camera_instance.register_decode_pcm_async(
                callback=on_decode_pcm_callback,
                channel=channel,
                multi_reg=False,
            )

        # 启动摄像头（拉流）
        await self.camera_instance.start_async(
            qualities=video_quality,
            pin_code=None,  # 如有摄像头 PIN 码就在这里填 4 位字符串
            enable_audio=True,  # 如需音频可改为 True
            enable_reconnect=True,  # 断线自动重连
            enable_record=False,
        )

    async def wait_for_data(self):
        print("开始接收摄像头数据，按 Ctrl+C 结束...")
        try:
            # 挂起主协程，持续接收回调
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("收到退出信号，正在停止摄像头...")
        finally:
            # 清理资源
            await self.cleanup()

    async def cleanup(self):
        await self.camera_instance.stop_async()
        await self.miot_client.deinit_async()

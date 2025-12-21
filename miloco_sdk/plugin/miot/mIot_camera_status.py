# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Test for get_status_async.
"""
import asyncio
import logging

from miloco_sdk.base import BaseApi
from miloco_sdk.plugin.miot.camera import MIoTCamera, MIoTCameraInstance
from miloco_sdk.utils.types import MIoTCameraInfo, MIoTCameraStatus, MIoTCameraVideoQuality

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
_LOGGER = logging.getLogger(__name__)


class MIoTCameraStatusF(BaseApi):

    async def get_status_async(self, device_info: dict):
        """测试 get_status_async 方法"""
        # 测试参数
        did = device_info["did"]
        model = device_info["model"]
        channels = device_info["extra"]["channel"]
        cloud_server = "cn"  # 云服务器区域

        # 创建 MIoTCameraInfo (需要提供必要的字段)
        camera_info = MIoTCameraInfo(
            did=did,
            name=device_info["name"],
            uid=str(device_info["uid"]),
            urn=f"urn:miot:device:{model}",
            model=model,
            manufacturer=model.split(".")[0],
            channel_count=len(channels),
            connect_type=device_info.get("pid", -1),
            pid=device_info["pid"],
            token=device_info["token"],
            online=device_info.get("isOnline", False),
            voice_ctrl=device_info.get("voice_ctrl", 0),
            order_time=device_info.get("orderTime", 0),
            camera_status=MIoTCameraStatus.DISCONNECTED,
        )

        _LOGGER.info("创建 MIoTCamera 实例...")
        miot_camera = MIoTCamera(
            cloud_server=cloud_server, access_token=self._client._access_token, loop=asyncio.get_event_loop()
        )

        try:
            # 获取库版本
            version = await miot_camera.get_camera_version_async()
            _LOGGER.info("libmiot_camera 版本: %s", version)

            # 创建摄像头实例
            _LOGGER.info("创建摄像头实例: %s", camera_info)
            camera_ins: MIoTCameraInstance = await miot_camera.create_camera_async(camera_info=camera_info)

            # 注册状态变化回调
            async def on_status_changed_async(did: str, status: MIoTCameraStatus):
                _LOGGER.info("状态变化回调: did=%s, status=%s", did, status)

            await camera_ins.register_status_changed_async(callback=on_status_changed_async)

            # 获取初始状态 (启动前)
            status_before = await camera_ins.get_status_async()
            _LOGGER.info("启动前摄像头状态: %s", status_before)

            # 启动摄像头
            _LOGGER.info("启动摄像头...")
            await camera_ins.start_async(qualities=MIoTCameraVideoQuality.LOW, enable_reconnect=True)

            # 等待连接
            await asyncio.sleep(3)

            # 获取状态 (启动后)
            status_after = await camera_ins.get_status_async()
            _LOGGER.info("启动后摄像头状态: %s", status_after)

            # 停止摄像头
            _LOGGER.info("停止摄像头...")
            await camera_ins.stop_async()

            # 获取停止后状态
            status_stopped = await camera_ins.get_status_async()
            _LOGGER.info("停止后摄像头状态: %s", status_stopped)

        except Exception as e:
            _LOGGER.error("测试过程中发生错误: %s", e)
            raise
        finally:
            # 清理资源
            _LOGGER.info("清理资源...")
            await miot_camera.destroy_camera_async(did=did)
            await miot_camera.deinit_async()
            _LOGGER.info("测试完成")

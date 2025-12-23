import hashlib
import inspect
from typing import Optional

import requests

from miloco_sdk.base import BaseApi
from miloco_sdk.plugin.authorize import Authorize
from miloco_sdk.plugin.home import Home
from miloco_sdk.plugin.miot.mIot_camera_status import MIoTCameraStatusF
from miloco_sdk.plugin.miot.mIot_camera_stream import MIoTCameraStream
from miloco_sdk.utils.common import get_device_id
from miloco_sdk.utils.const import OAUTH2_CLIENT_ID

# device_uuid = uuid.uuid4().hex
PROJECT_CODE: str = "mico"


def _is_api_endpoint(obj):
    return isinstance(obj, BaseApi)


class XiaomiClient:
    """
    小米客户端类，用于与小米设备进行通信和交互
    包含授权、家庭控制、摄像头流和状态管理等功能模块
    """

    _access_token: Optional[str]

    # 初始化各个功能模块的实例
    authorize = Authorize()
    home = Home()
    miot_camera_stream = MIoTCameraStream()
    miot_camera_status = MIoTCameraStatusF()

    def set_access_token(self, access_token: str):
        self._access_token = access_token

    def __init__(self, access_token: Optional[str] = None):
        self.client_id = OAUTH2_CLIENT_ID
        self._device_id = f"{PROJECT_CODE}.{get_device_id()}"
        self._state = hashlib.sha1(f"d={self._device_id}".encode("utf-8")).hexdigest()
        self._access_token = access_token

        self._http = requests.Session()
        self._http.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*",
            }
        )

    def __new__(cls, *args, **kwargs):
        self = super(XiaomiClient, cls).__new__(cls)
        api_endpoints = inspect.getmembers(self, _is_api_endpoint)
        for name, api in api_endpoints:
            api_cls = type(api)
            api = api_cls(self)
            setattr(self, name, api)
        return self

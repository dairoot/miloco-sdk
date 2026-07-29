import asyncio
import hashlib
import inspect
import json
import logging
import os
import platform
import time
import urllib.parse
from typing import Optional

logger = logging.getLogger(__name__)

import requests

from miloco_sdk.base import BaseApi
from miloco_sdk.configs import DATA_PATH
from miloco_sdk.plugin.authorize import Authorize
from miloco_sdk.plugin.device import Device
from miloco_sdk.plugin.home import Home
from miloco_sdk.plugin.miot.mIot_camera_status import MIoTCameraStatusF
from miloco_sdk.plugin.miot.mIot_camera_stream import MIoTCameraStream
from miloco_sdk.utils.common import get_device_id
from miloco_sdk.utils.const import OAUTH2_CLIENT_ID

# device_uuid = uuid.uuid4().hex
PROJECT_CODE: str = "mico"


def _check_system_support():
    """检查系统是否支持，仅支持 macOS、Linux 和 Windows (WSL)"""
    if platform.system() == "Windows":
        print(
            "不支持原生 Windows 系统。\n"
            "本 SDK 仅支持以下系统：\n"
            "  - macOS\n"
            "  - Linux\n"
            "  - Windows (WSL - Windows Subsystem for Linux)\n"
            "\n"
            "如果您在 Windows 上使用，请通过 WSL 运行。"
        )
        exit(1)


def _is_api_endpoint(obj):
    return isinstance(obj, BaseApi)


AUTH_FILE = os.path.join(DATA_PATH, "auth_info.json")


def _read_auth_info():
    if not os.path.exists(AUTH_FILE):
        return None
    with open(AUTH_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_auth_info(auth_info):
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(auth_info, f, ensure_ascii=True, indent=2)


class XiaomiClient:
    """
    小米客户端类，用于与小米设备进行通信和交互
    包含授权、家庭控制、摄像头流和状态管理等功能模块
    """

    _access_token: Optional[str]

    # 初始化各个功能模块的实例
    authorize = Authorize()
    home = Home()
    device = Device()
    miot_camera_stream = MIoTCameraStream()
    miot_camera_status = MIoTCameraStatusF()

    def __init__(self, access_token: Optional[str] = None):
        # 检查系统支持
        _check_system_support()

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

    def update_access_token(self):
        auth_info = _read_auth_info()
        if not auth_info:
            return

        # token 未过期，直接使用（提前10分钟刷新）
        if auth_info.get("created_at", 0) + auth_info.get("expires_in", 0) > int(time.time()) - 60 * 10:
            self._access_token = auth_info["access_token"]
            return

        # token 已过期，使用 refresh_token 刷新
        data = self.authorize.refresh_access_token_from_mico(auth_info["refresh_token"])
        auth_info = data["result"]
        auth_info["created_at"] = int(time.time())
        _save_auth_info(auth_info)
        logger.info("token 刷新成功，新 token 有效期 %d 秒", auth_info.get("expires_in", 0))
        self._access_token = auth_info["access_token"]

    def _start_token_refresh_timer(self):
        """启动定时刷新 token 的异步任务"""
        if getattr(self, "_refresh_task", None) and not self._refresh_task.done():
            self._refresh_task.cancel()

        self._refresh_task = asyncio.get_event_loop().create_task(self._token_refresh_loop())

    async def _token_refresh_loop(self):
        """每10分钟刷新一次 token"""
        while True:
            await asyncio.sleep(10 * 60)
            try:
                self.update_access_token()
            except Exception:
                pass

    def login(self):
        self.update_access_token()
        if self._access_token:
            self._start_token_refresh_timer()
            return

        # 本地无 token，通过扫码登录获取
        code_url = self.authorize.get_code_url()
        url = urllib.parse.urlparse(code_url)
        query_params = urllib.parse.parse_qs(url.query)
        code = query_params["code"][0]
        auth_info = self.authorize.get_access_token_from_mico(code)["result"]
        auth_info["created_at"] = int(time.time())

        # 保存 token 到本地
        _save_auth_info(auth_info)

        self._access_token = auth_info["access_token"]
        self._start_token_refresh_timer()

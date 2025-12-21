# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Test for get_status_async.
"""
import asyncio
import os
import sys

cur_path = os.path.abspath(__file__)
parent = os.path.dirname
sys.path.insert(0, parent(parent(cur_path)))

from miloco_sdk import XiaomiClient

access_token = os.getenv("ACCESS_TOKEN")

if not access_token:
    raise ValueError("ACCESS_TOKEN is not set")


class TestCameraStatus(object):
    async def run(self, device_info: dict):
        client = XiaomiClient(access_token=access_token)
        await client.miot_camera_status.get_status_async(device_info)


if __name__ == "__main__":
    device_info = {
        "did": "1177002050",
        "uid": 1449376110,
        "token": "5252734b6c4752576770666378316445",
        "name": "小米智能摄像机3 云台版",
        "pid": 0,
        "localip": "192.168.3.21",
        "mac": "B8:88:80:51:2E:2E",
        "ssid": "HZJ213",
        "bssid": "62:E9:9D:A2:BF:99",
        "rssi": -57,
        "longitude": "0.00000000",
        "latitude": "0.00000000",
        "city_id": 101280601,
        "show_mode": 1,
        "model": "chuangmi.camera.069a01",
        "permitLevel": 16,
        "isOnline": True,
        "spec_type": "urn:miot-spec-v2:device:camera:0000A01C:chuangmi-069a01:4",
        "extra": {
            "isSetPincode": 0,
            "pincodeType": 0,
            "fw_version": "5.3.1_0525",
            "isSubGroup": False,
            "showGroupMember": False,
            "split": {},
            "channel": [1],
        },
        "orderTime": 1764166529,
        "freqFlag": True,
        "hide_mode": 0,
        "comFlag": 961,
        "carPicInfo": "",
        "room_id": "169001360387",
        "room_name": "卧室",
    }
    asyncio.run(TestCameraStatus().run(device_info))

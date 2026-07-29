#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import time
import unittest

cur_path = os.path.abspath(__file__)
parent = os.path.dirname
sys.path.insert(0, parent(parent(cur_path)))

from miloco_sdk import XiaomiClient
from miloco_sdk.plugin.device import resolve_switches, spec_type_name

access_token = os.getenv("ACCESS_TOKEN")

# 要控制的设备 did，例如米家智能插座（cuco.plug.v3）
did = os.getenv("DEVICE_DID")


def build_spec(urn, services):
    """按 miot-spec.org 的返回结构造一份精简 spec。"""
    return {
        "type": urn,
        "services": [
            {
                "iid": siid,
                "type": f"urn:miot-spec-v2:service:{name}:0000{siid:04X}:test:1",
                "description": name,
                "properties": props,
            }
            for siid, name, props in services
        ],
    }


def on_prop(piid, access=("read", "write", "notify")):
    return {"iid": piid, "type": "urn:miot-spec-v2:property:on:00000006:test:1", "access": list(access)}


class TestSpecTypeName(unittest.TestCase):
    """纯解析逻辑，不需要网络。"""

    def test_spec_type_name(self):
        self.assertEqual(spec_type_name("urn:miot-spec-v2:device:outlet:0000A002:cuco-v3:1"), "outlet")
        self.assertEqual(spec_type_name("urn:miot-spec-v2:service:switch:00007820:cuco-v3:1"), "switch")
        self.assertEqual(spec_type_name("urn:miot-spec-v2:property:on:00000006:cuco-v3:1"), "on")
        self.assertEqual(spec_type_name(""), "")


class TestResolveSwitches(unittest.TestCase):
    """主开关定位，不需要网络。"""

    def test_outlet_picks_switch_service(self):
        """cuco.plug.v3 有 6 个可写 on，只有 switch 是通断电。"""
        urn = "urn:miot-spec-v2:device:outlet:0000A002:cuco-v3:1"
        spec = build_spec(
            urn,
            [
                (2, "switch", [on_prop(1)]),
                (4, "charging-protection", [on_prop(1)]),
                (8, "quick-countdown", [on_prop(1)]),
                (9, "max-power-limit", [on_prop(1)]),
                (10, "over-use-ele-alert", [on_prop(1)]),
                (13, "indicator-light", [on_prop(1)]),
            ],
        )
        switches = resolve_switches(spec, urn)
        self.assertEqual(len(switches), 6)
        # 主开关唯一且排在最前
        self.assertEqual([s for s in switches if s["primary"]], [switches[0]])
        self.assertEqual((switches[0]["siid"], switches[0]["piid"]), (2, 1))

    def test_hood_picks_main_service_not_light(self):
        """油烟机的 light.on 是照明灯，不能当主开关。"""
        urn = "urn:miot-spec-v2:device:hood:0000A00D:viomi-v1:1"
        spec = build_spec(urn, [(2, "hood", [on_prop(1)]), (4, "light", [on_prop(1)])])
        switches = resolve_switches(spec, urn)
        self.assertEqual((switches[0]["siid"], switches[0]["service"]), (2, "hood"))
        self.assertFalse([s for s in switches if s["service"] == "light"][0]["primary"])

    def test_multi_gang_switch(self):
        """多键墙壁开关每键一路，都是主开关。"""
        urn = "urn:miot-spec-v2:device:switch:0000A003:lumi-b2lacn02:1"
        spec = build_spec(urn, [(2, "switch", [on_prop(1)]), (3, "switch", [on_prop(1)])])
        switches = resolve_switches(spec, urn)
        self.assertEqual([(s["siid"], s["primary"]) for s in switches], [(2, True), (3, True)])

    def test_camera_alias(self):
        """摄像头的主开关在 camera-control 服务下。"""
        urn = "urn:miot-spec-v2:device:camera:0000A01C:chuangmi-ipc019:1"
        spec = build_spec(urn, [(2, "camera-control", [on_prop(1)])])
        self.assertTrue(resolve_switches(spec, urn)[0]["primary"])

    def test_readonly_on_is_ignored(self):
        """只读的 on 不是可控开关。"""
        urn = "urn:miot-spec-v2:device:vacuum:0000A006:roborock-a01:1"
        spec = build_spec(urn, [(2, "vacuum", [on_prop(1, access=("read", "notify"))])])
        self.assertEqual(resolve_switches(spec, urn), [])


@unittest.skipUnless(access_token and did, "需要设置 ACCESS_TOKEN 和 DEVICE_DID")
class TestDevice(unittest.TestCase):

    def setUp(self):
        self.client = XiaomiClient(access_token=access_token)

    def test_find_switch_list(self):
        switches = self.client.device.find_switch_list(did)
        for switch in switches:
            print(switch)
        self.assertTrue(switches, "该设备没有可写的 on 属性")

    def test_get_power(self):
        print("当前状态:", self.client.device.get_power(did))

    def test_turn_on_off(self):
        self.client.device.turn_on(did)
        time.sleep(2)
        self.assertTrue(self.client.device.get_power(did))

        self.client.device.turn_off(did)
        time.sleep(2)
        self.assertFalse(self.client.device.get_power(did))


if __name__ == "__main__":
    unittest.main()

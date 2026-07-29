"""设备开关控制示例：列设备 -> 查当前状态 -> 开 / 关。

米家智能插座（cuco.plug.v3）、灯、风扇等只要 spec 里有可写的 on 属性，都走这条路径。

运行：
    uv run python examples/device_control.py
"""

import asyncio

from miloco_sdk import XiaomiClient
from miloco_sdk.cli.utils import print_device_list


async def run():
    client = XiaomiClient()
    client.login()

    device_list = client.home.get_device_list()
    online_devices = [d for d in device_list if d.get("isOnline", False)]

    if not online_devices:
        print("\n设备列表: 暂无在线设备")
        return

    print_device_list(online_devices)
    index = input("请输入要控制的设备序号: ")
    try:
        device_info = online_devices[int(index) - 1]
    except Exception as e:
        print(f"输入错误: {e}")
        return

    did = device_info["did"]
    print(f"\n设备: {device_info['name']} ({device_info['model']})")

    # 列出该设备所有可控开关（多键开关会有多路，插座一般是主开关 + 指示灯）
    switches = client.device.find_switch_list(did)
    if not switches:
        print("该设备不支持开关控制")
        return
    for switch in switches:
        flag = "主开关" if switch["primary"] else "次开关"
        print(f"  [{flag}] siid={switch['siid']} piid={switch['piid']} {switch['service']} {switch['description']}")

    # 不传 siid/piid 时自动用主开关
    print(f"\n当前状态: {'开' if client.device.get_power(did) else '关'}")

    action = input("输入 on 开 / off 关 / toggle 切换: ").strip().lower()
    if action == "on":
        client.device.turn_on(did)
    elif action == "off":
        client.device.turn_off(did)
    elif action == "toggle":
        client.device.toggle(did)
    else:
        print("未知操作")
        return

    print(f"操作完成，当前状态: {'开' if client.device.get_power(did) else '关'}")


if __name__ == "__main__":
    asyncio.run(run())

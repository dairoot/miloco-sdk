import base64
import json
import os

from miloco_sdk.configs import DATA_PATH


def get_display_width(text):
    """计算字符串在终端中的实际显示宽度（中文字符占2个宽度）"""
    width = 0
    for char in text:
        # 中文字符、全角字符等占2个宽度
        if ord(char) > 127:
            width += 2
        else:
            width += 1
    return width


def pad_string(text, width, align="<"):
    """填充字符串到指定显示宽度"""
    display_width = get_display_width(text)
    padding = width - display_width
    if padding <= 0:
        return text
    if align == "<":
        return text + " " * padding
    elif align == ">":
        return " " * padding + text
    else:  # center
        left = padding // 2
        right = padding - left
        return " " * left + text + " " * right


def get_auth_info(client):

    auth_file = os.path.join(DATA_PATH, "auth_info.json")
    if os.path.exists(auth_file):
        with open(auth_file, "r", encoding="utf-8") as f:
            auth_info = json.load(f)
        return auth_info

    auth_url = client.authorize.gen_auth_url(skip_confirm=True)
    # 请用户在浏览器中打开授权页面
    print(f"请在浏览器中打开授权链接: \n{auth_url}")
    base64_code = input("\n请输入授权码: ")
    try:
        code_info = json.loads(base64.b64decode(base64_code).decode("utf-8"))
        code_info["code"]
    except Exception as e:
        print(f"授权码格式错误: {e}")
        return

    auth_info = client.authorize.get_access_token_from_mico(code_info["code"])["result"]

    with open(auth_file, "w", encoding="utf-8") as f:
        json.dump(auth_info, f, ensure_ascii=True, indent=2)

    return auth_info


def print_device_list(device_list):
    """打印设备列表"""

    print("\n设备列表:")
    separator = "-" * 70
    print(separator)
    header = f"{pad_string('序号', 8)}{pad_string('房间', 16)}{pad_string('设备名称', 36)}"
    print(header)
    print(separator)

    for idx, device in enumerate(device_list, 1):
        room_name = device.get("room_name", "未知")
        device_name = device.get("name", "未知")
        row = f"{pad_string(str(idx), 8)}{pad_string(room_name, 16)}{pad_string(device_name, 36)}"
        print(row)

    print(separator)

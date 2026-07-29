# Miloco SDK

小米 Miloco SDK for Python - 用于与小米智能设备进行交互的 Python SDK。

> 本项目是基于 [Xiaomi Miloco](https://github.com/XiaoMi/xiaomi-miloco) 开源框架封装而成的 Python SDK，提供了更便捷的 Python 接口来访问小米智能设备的功能。


## 功能特性

- 🔐 **授权认证** - 支持 OAuth2 授权流程，自动管理访问令牌
- 🏠 **家庭管理** - 获取家庭列表、房间信息和设备列表
- 📹 **摄像头流媒体** - 支持摄像头视频流获取和处理
  - JPEG 图片解码回调
  - 原始视频流处理
  - RTSP 推流支持
- 📊 **设备状态** - 查询和管理设备状态
- 🔌 **设备控制** - 开关设备（插座、灯、风扇等），读写 MIoT 属性、调用动作
- 🤖 **LLM 集成** - 支持与大型语言模型集成，实现智能对话
- 🔧 **MCP 工具** - 支持 Model Context Protocol (MCP) 工具调用
- 🖼️ **视觉理解** - 支持图像视觉理解功能


## 系统要求

- Python 3.12+
- 支持 macOS、Linux 和 Windows (WSL)。


## 安装

### 从源码安装

```bash
# pip install git+https://github.com/dairoot/miloco-sdk.git

pip install uv
uv sync --extra dev
```

## 快速开始

### 1. 终端使用

项目提供了命令行工具，支持交互式对话和工具调用：

需要先配置环境变量：
```bash
export OPENAI_API_KEY=大模型的API密钥
export OPENAI_MODEL=大模型的模型名称
export OPENAI_BASE_URL=大模型的API地址
```

运行命令行工具：
```bash
uv run python -m miloco_sdk
```

运行 Web 服务器示例：
```bash
uv run python examples/web.py
```

### 2. 编程使用

SDK 提供了丰富的示例代码，位于 [examples/](examples/) 目录下，帮助您快速上手：

| 示例文件 | 功能描述 |
|---------|---------|
| `examples/web.py` | Web 服务器示例，支持实时播放 HEVC 视频流，并进行目标检测，Docker 一键部署 |
| `examples/mcp_server.py` | MCP 服务器示例，支持与大模型集成，实现智能对话功能 |
| `examples/stream_to_jpg.py` | 摄像头图片获取示例，支持实时获取并保存为 JPEG 图片文件 |
| `examples/stream_to_video.py` | 摄像头视频流获取示例，支持实时播放 HEVC 视频流 |
| `examples/stream_to_audio.py` | 摄像头音频流获取示例，支持实时播放 PCM 音频流 |
| `examples/yolo.py` | 摄像头视频流获取示例，支持实时播放 HEVC 视频流，并进行目标检测 |
| `examples/rtsp/` | RTSP 推流示例，使用 go2rtc 作为流媒体服务器，支持浏览器 WebRTC 观看，Docker 一键部署 |
| `examples/device_control.py` | 设备开关控制示例，支持查询状态、开 / 关 / 切换 |

### 3. 设备开关控制

设备能力由 MIoT spec 描述，SDK 会自动定位设备主开关，不需要为型号写适配。
米家智能插座（`cuco.plug.v3`）、灯、风扇、空调等都是同一套调用：

```python
from miloco_sdk import XiaomiClient

client = XiaomiClient()
client.login()

did = "123456789"  # 设备 did，可从 client.home.get_device_list() 获取

client.device.turn_on(did)          # 开
client.device.turn_off(did)         # 关
client.device.toggle(did)           # 切换
client.device.get_power(did)        # 查询当前是开还是关 -> True / False
```

多路开关（多键墙壁开关等）可以先列出所有可控开关，再指定某一路：

```python
# [{'siid': 2, 'piid': 1, 'service': 'switch', 'description': 'Switch', 'primary': True}, ...]
switches = client.device.find_switch_list(did)

client.device.turn_off(did, siid=2, piid=1)
```

> `primary=False` 的是指示灯、倒计时、功率上限等功能开关，并不控制通断电。
> 例如 `cuco.plug.v3` 有 6 个可写的 `on` 属性，只有 `switch` 服务下的那个才是通断电，
> SDK 只会自动选主开关；遇到定位不了的设备会直接报错并列出候选，不会误选。

还可以直接读写任意 MIoT 属性 / 调用动作：

```python
client.device.get_prop(did, siid=11, piid=1)          # 读属性（插座功耗）
client.device.set_prop(did, siid=2, piid=1, value=True)  # 写属性
client.device.call_action(did, siid=5, aiid=1, in_=[])   # 调用动作
```

## 许可证

本项目基于 [Xiaomi Miloco](https://github.com/XiaoMi/xiaomi-miloco) 开源框架开发，因此必须遵守 [Xiaomi Miloco License Agreement](https://github.com/XiaoMi/xiaomi-miloco/blob/main/LICENSE.md)。



## 致谢

感谢 [Xiaomi Miloco](https://github.com/XiaoMi/xiaomi-miloco) 项目团队提供的优秀开源框架。

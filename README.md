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
- 🤖 **LLM 集成** - 支持与大型语言模型集成，实现智能对话
- 🔧 **MCP 工具** - 支持 Model Context Protocol (MCP) 工具调用
- 🖼️ **视觉理解** - 支持图像视觉理解功能


## 系统要求

支持 macOS、Linux 和 Windows (WSL)。


## 安装

### 从源码安装

```bash
pip install git+https://github.com/dairoot/miloco-sdk.git
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
python -m miloco_sdk
```

### 2. 编程使用

SDK 提供了丰富的示例代码，位于 [examples/](examples/) 目录下，帮助您快速上手：

| 示例文件 | 功能描述 |
|---------|---------|
| `examples/mcp_server.py` | MCP 服务器示例，支持与大模型集成，实现智能对话功能 |
| `examples/stream_to_jpg.py` | 摄像头图片获取示例，支持实时获取并保存为 JPEG 图片文件 |
| `examples/stream_to_video.py` | 摄像头视频流获取示例，支持实时播放 HEVC 视频流 |
| `examples/stream_to_audio.py` | 摄像头音频流获取示例，支持实时播放 PCM 音频流 |
| `examples/yolo.py` | 摄像头视频流获取示例，支持实时播放 HEVC 视频流，并进行目标检测 |
| `examples/rtsp.py` | RTSP 推流示例，支持将摄像头视频流推送到 RTSP 服务器 |


## 许可证

本项目基于 [Xiaomi Miloco](https://github.com/XiaoMi/xiaomi-miloco) 开源框架开发，因此必须遵守 [Xiaomi Miloco License Agreement](https://github.com/XiaoMi/xiaomi-miloco/blob/main/LICENSE.md)。



## 致谢

感谢 [Xiaomi Miloco](https://github.com/XiaoMi/xiaomi-miloco) 项目团队提供的优秀开源框架。

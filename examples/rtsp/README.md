# RTSP 推流示例

本文档介绍 `examples/rtsp` 的两种运行方式：Docker 一键部署（推荐）和手动部署。

## 前置条件

- 已安装 Docker（使用 Docker 方式时）
- 本机可访问摄像头设备
- 使用手动方式时，已安装 `uv`

## 方式一：Docker 一键部署（推荐）

1. 进入示例目录：

```bash
cd examples/rtsp
```

2. 启动服务：

```bash
docker compose up -d
```

3. （可选）进入推流容器交互界面
   仅在有多台摄像头、需要手动选择设备时执行：

```bash
docker attach rtsp-rtsp-pusher-1
```

4. 在浏览器打开以下地址查看实时画面：

`http://127.0.0.1:1984/stream.html?src=live`

## 方式二：手动部署

1. 启动 `go2rtc`：
   - 下载：<https://github.com/AlexxIT/go2rtc/releases>
   - 在当前目录执行：

```bash
go2rtc -config go2rtc.yaml
```

2. 运行 RTSP 推流脚本：

```bash
# 仅推送视频
uv run python examples/rtsp/rtsp.py
```

```bash
# 推送视频 + 音频
uv run python examples/rtsp/rtsp.py --audio
```

3. 在浏览器打开以下地址查看实时画面：

`http://127.0.0.1:1984/stream.html?src=live`

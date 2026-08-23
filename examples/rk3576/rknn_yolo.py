"""在 RK3576 的 NPU 上跑 yolo11n。

这块板子是 Cortex-A53/A72（ARMv8.0），PyPI 上的 torch aarch64 wheel 是按 ARMv8.2+ 编的，
一跑卷积就 SIGILL，所以 ultralytics 在这里用不了。改成 NPU 推理：

    rknn_model_zoo 的 yolo11n.onnx --(rknn-toolkit2)--> yolo11n_fp.rknn --(rknnlite)--> NPU

模型的 9 个输出是 3 个尺度 x (box 64通道 DFL, 类别 80通道, score_sum)，后处理照
rknn_model_zoo 的实现，只是把里面的 torch 换成了 numpy。
"""
import cv2
import numpy as np
from rknnlite.api import RKNNLite

MODEL_PATH = "yolo11n_int8.rknn"
IMG_SIZE = 640
OBJ_THRESH = 0.25
NMS_THRESH = 0.45
# 每 N 帧才过一次 NPU，中间帧复用上次的框。inference() 单次 34ms，其中 30ms 是
# 主机侧反量化 + NCHW 转置（lite2 的 Python API 没法跳过），隔帧是最划算的省法。
DETECT_EVERY = 2

CLASSES = (
    "person", "bicycle", "car", "motorbike", "aeroplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "sofa",
    "pottedplant", "bed", "diningtable", "toilet", "tvmonitor", "laptop", "mouse", "remote", "keyboard",
    "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
)

# 只显示这几类，设成 () 表示不过滤
SHOW = ("cat", "bed", "cell phone", "person", "hair drier", "scissors", "refrigerator", "book", "chair", "sofa")
SHOW_IDS = np.array([CLASSES.index(name) for name in SHOW]) if SHOW else None


def _decode_branch(box_out, cls_out):
    """解一个尺度的输出，返回过阈值的 (xyxy, 类别, 分数)。

    先用类别分筛掉绝大部分格子，只对活下来的几十个格子算 DFL —— 对全部 8400 个
    格子做 softmax 要 24ms，这样只要 2ms。
    """
    grid_h, grid_w = cls_out.shape[2:4]
    stride = IMG_SIZE // grid_h

    cls = cls_out.transpose(0, 2, 3, 1).reshape(-1, cls_out.shape[1])
    scores = cls.max(axis=1)
    idx = np.where(scores >= OBJ_THRESH)[0]
    if idx.size == 0:
        return None

    # 只对候选格子解 DFL：(K,64) -> (K,4,16) softmax -> 期望值
    box = box_out.transpose(0, 2, 3, 1).reshape(-1, box_out.shape[1])[idx].reshape(-1, 4, 16)
    box = box - box.max(axis=2, keepdims=True)
    np.exp(box, out=box)
    box /= box.sum(axis=2, keepdims=True)
    dist = (box * np.arange(16, dtype=np.float32)).sum(axis=2)  # (K,4) 上下左右距离

    grid = np.stack((idx % grid_w, idx // grid_w), axis=1) + 0.5
    xyxy = np.concatenate(((grid - dist[:, 0:2]) * stride, (grid + dist[:, 2:4]) * stride), axis=1)
    return xyxy, cls[idx].argmax(axis=1), scores[idx]


def _nms(boxes, scores):
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        ovr = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
        order = order[np.where(ovr <= NMS_THRESH)[0] + 1]
    return np.array(keep)


class RknnYolo:
    """加载 .rknn 模型，对 BGR 帧做检测并把框画上去。"""

    def __init__(self, model_path: str = MODEL_PATH):
        self.rknn = RKNNLite()
        if self.rknn.load_rknn(model_path) != 0:
            raise RuntimeError(f"加载模型失败: {model_path}")
        # RK3576 的 NPU 有两个核，双核比单核快约 20%
        if self.rknn.init_runtime(core_mask=RKNNLite.NPU_CORE_0_1) != 0:
            raise RuntimeError("NPU init_runtime 失败")
        self._seq = 0
        self._last = (None, None, None)

    def _letterbox(self, bgr):
        h, w = bgr.shape[:2]
        ratio = min(IMG_SIZE / h, IMG_SIZE / w)
        nh, nw = int(round(h * ratio)), int(round(w * ratio))
        canvas = np.full((IMG_SIZE, IMG_SIZE, 3), 114, dtype=np.uint8)
        top, left = (IMG_SIZE - nh) // 2, (IMG_SIZE - nw) // 2
        canvas[top : top + nh, left : left + nw] = cv2.resize(bgr, (nw, nh))
        return canvas, ratio, left, top

    def detect(self, bgr):
        """返回 (boxes_xyxy, classes, scores)，坐标已还原到原图尺寸；没检到返回 (None, None, None)。"""
        canvas, ratio, pad_x, pad_y = self._letterbox(bgr)
        rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)[np.newaxis, ...]  # 模型要 4 维 NHWC
        outputs = self.rknn.inference(inputs=[rgb], data_format=["nhwc"])

        # 9 个输出 = 3 个尺度 x (box, 类别, score_sum)，score_sum 这里用不上
        decoded = [d for d in (_decode_branch(outputs[i * 3], outputs[i * 3 + 1]) for i in range(3)) if d]
        if not decoded:
            return None, None, None

        boxes = np.concatenate([d[0] for d in decoded])
        classes = np.concatenate([d[1] for d in decoded])
        scores = np.concatenate([d[2] for d in decoded])

        if SHOW_IDS is not None:
            keep = np.isin(classes, SHOW_IDS)
            if not keep.any():
                return None, None, None
            boxes, classes, scores = boxes[keep], classes[keep], scores[keep]

        # 按类别分别做 NMS
        nb, nc, ns = [], [], []
        for c in set(classes):
            idx = np.where(classes == c)[0]
            k = _nms(boxes[idx], scores[idx])
            if len(k):
                nb.append(boxes[idx][k])
                nc.append(classes[idx][k])
                ns.append(scores[idx][k])
        if not nb:
            return None, None, None

        boxes = np.concatenate(nb)
        # 去掉 letterbox 的补边并还原到原图尺寸
        boxes[:, [0, 2]] = (boxes[:, [0, 2]] - pad_x) / ratio
        boxes[:, [1, 3]] = (boxes[:, [1, 3]] - pad_y) / ratio
        return boxes, np.concatenate(nc), np.concatenate(ns)

    def detect_and_draw(self, bgr):
        """在原图上画框，返回同一张图（原地修改）。每 DETECT_EVERY 帧才真跑一次 NPU。"""
        if self._seq % DETECT_EVERY == 0:
            self._last = self.detect(bgr)
        self._seq += 1
        boxes, classes, scores = self._last
        if boxes is None:
            return bgr
        for box, cl, score in zip(boxes, classes, scores):
            x1, y1, x2, y2 = (int(v) for v in box)
            cv2.rectangle(bgr, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(
                bgr, f"{CLASSES[cl]} {score:.2f}", (x1, max(y1 - 6, 12)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2,
            )
        return bgr


if __name__ == "__main__":
    import sys
    import time

    img = cv2.imread(sys.argv[1] if len(sys.argv) > 1 else "camera.jpg")
    yolo = RknnYolo()

    boxes, classes, scores = yolo.detect(img)
    if boxes is None:
        print("没检测到目标")
    else:
        for box, cl, score in zip(boxes, classes, scores):
            print(f"  {CLASSES[cl]:<12} {score:.3f}  {[int(v) for v in box]}")

    n = 30
    t0 = time.perf_counter()
    for _ in range(n):
        yolo.detect(img)
    dt = (time.perf_counter() - t0) / n
    print(f"平均单帧 {dt*1000:.1f} ms ({1/dt:.1f} fps)")

    cv2.imwrite("rknn_out.jpg", yolo.detect_and_draw(img))
    print("结果已写入 rknn_out.jpg")

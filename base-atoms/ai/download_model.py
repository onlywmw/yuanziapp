# download_model.py — 拉取 bge-small-zh-v1.5 ONNX 模型与词表（一次性脚本）
"""
选型：BAAI/bge-small-zh-v1.5（MIT 协议，24M 参数，512 维），
使用 HuggingFace Xenova/bge-small-zh-v1.5 提供的现成 ONNX：
- onnx/model.onnx（约 90MB）
- vocab.txt（bert 中文词表，21128 词）

用法：
    python download_model.py [目标目录]

目录解析优先级：命令行参数 > AI_MODEL_PATH 所在目录 > 本目录 models/。
下载完成后将 AI_MODEL_PATH 指向 model.onnx 即可启用 OnnxProvider。
国内网络可设置 HF_ENDPOINT=https://hf-mirror.com 走镜像。
模型文件不入 git（见仓库 .gitignore）。本脚本仅在准备阶段联网，
运行期推理永远本地、不上云。
"""
import os
import shutil
import sys
import urllib.request
from pathlib import Path

BASE_URL = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
REPO = "Xenova/bge-small-zh-v1.5"
MODEL_URL = f"{BASE_URL}/{REPO}/resolve/main/onnx/model.onnx"
VOCAB_URL = f"{BASE_URL}/{REPO}/resolve/main/vocab.txt"


def _download(url, dest):
    """流式下载到临时文件再改名；目标已存在则跳过（幂等）。"""
    dest = Path(dest)
    if dest.is_file():
        print(f"已存在，跳过：{dest}（{dest.stat().st_size / 1e6:.1f} MB）")
        return
    tmp = dest.with_name(dest.name + ".tmp")
    print(f"下载 {url}\n  → {dest}")
    req = urllib.request.Request(url, headers={"User-Agent": "yuanzi-system.ai/2.0"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as f:
        shutil.copyfileobj(resp, f, length=1024 * 256)
    tmp.replace(dest)
    print(f"  完成（{dest.stat().st_size / 1e6:.1f} MB）")


def main():
    if len(sys.argv) > 1:
        out_dir = Path(sys.argv[1])
        model_path = out_dir / "model.onnx"
    elif os.environ.get("AI_MODEL_PATH"):
        model_path = Path(os.environ["AI_MODEL_PATH"])
        out_dir = model_path.parent
    else:
        out_dir = Path(__file__).resolve().parent / "models"
        model_path = out_dir / "model.onnx"
    out_dir.mkdir(parents=True, exist_ok=True)

    _download(VOCAB_URL, out_dir / "vocab.txt")
    _download(MODEL_URL, model_path)

    print("\n全部就绪。启用方式：")
    print(f"  AI_MODEL_PATH={model_path}")
    print("（vocab.txt 需与 model.onnx 同目录，OnnxProvider 会自动加载）")


if __name__ == "__main__":
    main()

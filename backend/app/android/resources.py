"""Shared Android model assets and cleanup of generated account caches."""
from pathlib import Path

MODELS = ("common_old.onnx", "common_tencent.onnx", "calc_det.onnx")
LEGACY_RESOURCES = (*MODELS, "tencentCollect.exe", "tencentPowSolve.exe")


def prepare_resources(data_dir: Path, model_dir: Path):
    for name in MODELS:
        path = model_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError("OCR 模型资源不完整，请重新安装应用")
    root = data_dir / "console"
    if not root.is_dir() or root.is_symlink():
        return
    for account in root.iterdir():
        if not account.name.isdigit() or account.is_symlink() or not account.is_dir():
            continue
        assets = account / "assets"
        if not assets.is_dir() or assets.is_symlink():
            continue
        for name in LEGACY_RESOURCES:
            path = assets / name
            if path.is_file() or path.is_symlink():
                path.unlink()

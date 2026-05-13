#!/usr/bin/env python3
"""
将 img/ 目录下的 logo 图片统一处理为 64x64 的 favicon PNG，
存入 website/static/images/favicons/ 目录。
"""
import sys
from pathlib import Path

# Pillow / pillow-heif
from PIL import Image
import pillow_heif
pillow_heif.register_heif_opener()

# 项目中所有候选图片（手动列出，确保顺序固定）
SRC_FILES = [
    "img/IMG_20260514_023847.JPG",
    "img/IMG_20260514_023955.PNG",
    "img/IMG_20260514_024025.PNG",
    "img/IMG_20260514_024235.HEIC",
    "img/IMG_20260514_024308.HEIC",
]

OUT_DIR = Path("website/static/images/favicons")
SIZE = (64, 64)


def convert_image(src_path: Path, out_path: Path) -> bool:
    """将一张图片转换为 64x64 PNG favicon，返回成功与否。"""
    try:
        img = Image.open(src_path)
        # 确保是正方形：取短边居中裁剪
        w, h = img.size
        if w != h:
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            img = img.crop((left, top, left + side, top + side))
        # 缩放到 64x64
        img = img.resize(SIZE, Image.LANCZOS)
        # 转 RGB（去除 alpha 通道，防止 PNG 报错）
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")
        # 保存为 PNG
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, "PNG")
        print(f"  ✓ {src_path.name} → {out_path.name}  ({w}x{w} → {SIZE[0]}x{SIZE[1]})")
        return True
    except Exception as e:
        print(f"  ✗ {src_path.name} 转换失败: {e}")
        return False


def main():
    project_root = Path(__file__).resolve().parent.parent
    out_dir = project_root / OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"输出目录: {out_dir}")
    print(f"目标尺寸: {SIZE[0]}×{SIZE[1]}px\n")

    success = 0
    for i, rel_path_str in enumerate(SRC_FILES, start=1):
        src = project_root / rel_path_str
        if not src.exists():
            print(f"  ! {rel_path_str} 不存在，跳过")
            continue
        out_name = f"favicon{i}.png"
        out = out_dir / out_name
        if convert_image(src, out):
            success += 1

    print(f"\n处理完成: {success}/{len(SRC_FILES)} 张成功")
    return 0 if success == len(SRC_FILES) else 1


if __name__ == "__main__":
    sys.exit(main())

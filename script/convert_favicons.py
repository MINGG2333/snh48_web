#!/usr/bin/env python3
"""
将 img/ 目录下的 logo 图片统一处理为 64x64 的 favicon PNG，
存入 website/static/images/favicons/ 目录。

用法:
  conda run -n koudai48 python script/convert_favicons.py

说明:
  - 自动扫描 img/ 目录下所有图片（JPG/PNG/HEIC）
  - 按文件名排序后依次输出为 favicon1.png, favicon2.png ...
  - 每次运行会清空并重建 favicons 目录
"""
import shutil
import sys
from pathlib import Path

# Pillow / pillow-heif
from PIL import Image
import pillow_heif
pillow_heif.register_heif_opener()

IMG_DIR = Path("img")
OUT_DIR = Path("website/static/images/favicons")
SIZE = (64, 64)

# 支持的图片扩展名
EXTENSIONS = (".jpg", ".jpeg", ".png", ".heic", ".heif")


def convert_image(src_path: Path, out_path: Path) -> bool:
    """将一张图片转换为 64x64 PNG favicon，返回成功与否。"""
    try:
        img = Image.open(src_path)
        w, h = img.size
        # 确保是正方形：取短边居中裁剪
        if w != h:
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            img = img.crop((left, top, left + side, top + side))
        # 缩放到 64x64
        img = img.resize(SIZE, Image.LANCZOS)
        # 转 RGB/RGBA 防止保存报错
        if img.mode in ("P", "PA"):
            img = img.convert("RGBA")
        elif img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        # 保存为 PNG
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, "PNG")
        print(f"  ✓ {src_path.name} ({w}x{h}) → {out_path.name}")
        return True
    except Exception as e:
        print(f"  ✗ {src_path.name} 转换失败: {e}")
        return False


def main():
    project_root = Path(__file__).resolve().parent.parent
    src_dir = project_root / IMG_DIR
    out_dir = project_root / OUT_DIR

    # 扫描 img/ 目录下所有图片（排除备案图标）
    EXCLUDED = {"备案图标.png"}
    images = sorted(
        [f for f in src_dir.iterdir() if f.suffix.lower() in EXTENSIONS and f.name not in EXCLUDED],
        key=lambda f: f.name,
    )

    if not images:
        print(f"! {src_dir} 下没有找到图片")
        print(f"  支持的格式: {', '.join(EXTENSIONS)}")
        return 1

    print(f"源目录: {src_dir}")
    print(f"输出目录: {out_dir}")
    print(f"目标尺寸: {SIZE[0]}×{SIZE[1]}px")
    print(f"找到 {len(images)} 张图片:\n")

    # 清空旧输出目录
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    success = 0
    for i, src in enumerate(images, start=1):
        out_name = f"favicon{i}.png"
        out = out_dir / out_name
        if convert_image(src, out):
            success += 1

    print(f"\n处理完成: {success}/{len(images)} 张成功")
    return 0 if success == len(images) else 1


if __name__ == "__main__":
    sys.exit(main())

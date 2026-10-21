"""核心转换逻辑（与 GUI / CLI 解耦，便于单元测试）。"""

import argparse
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image, ImageOps

# 支持的图片扩展名（小写）
IMAGE_EXTENSIONS = (".webp", ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".tif")

# 各目标格式的 PIL 常量映射
FORMAT_ALIASES = {
    "JPEG": "JPEG",
    "JPG": "JPEG",
    "PNG": "PNG",
    "BMP": "BMP",
    "GIF": "GIF",
    "TIFF": "TIFF",
    "TIF": "TIFF",
    "WEBP": "WEBP",
}


# ------------------------------------------------------------------ 统计

@dataclass
class ConversionStats:
    """一次批量转换的统计信息。"""

    total: int = 0
    success: int = 0
    failed: int = 0
    cancelled: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    errors: list = field(default_factory=list)

    @property
    def finished(self) -> bool:
        return self.total > 0 and self.success + self.failed + self.cancelled == self.total

    @property
    def savings_pct(self):
        """输出相对输入的总体积变化百分比（正数 = 体积减小）。无输入字节时返回 None。"""
        if self.bytes_in <= 0:
            return None
        return round((self.bytes_in - self.bytes_out) / self.bytes_in * 100, 1)

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------ 查找

def find_image_files(folder, recursive=True):
    """列出文件夹中的图片文件，返回排序后的 Path 列表。"""
    root = Path(folder)
    if not root.exists() or not root.is_dir():
        return []

    def _match(p: Path) -> bool:
        return p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS

    if recursive:
        return sorted(p for p in root.rglob("*") if _match(p))
    return sorted(p for p in root.iterdir() if _match(p))


# ------------------------------------------------------------------ 单文件

def _save_quality_args(fmt: str, quality: int) -> dict:
    """根据目标格式返回 save() 的质量参数。"""
    q = max(1, min(100, int(quality)))
    if fmt in ("JPEG", "WEBP"):
        return {"quality": q}
    if fmt == "TIFF":
        return {"compression": "tiff_lzw"}
    return {}


def _exif_needs_transpose(img) -> bool:
    try:
        orientation = img.getexif().get(0x0112, 1)
    except Exception:  # noqa: BLE001 - 非 JPEG / 解析失败
        return False
    return orientation not in (0, 1)


def _save_gif_all_frames(img, dest: Path):
    """保存动态 GIF 的全部帧（含时长与无限循环）。"""
    frames, durations = [], []
    for i in range(img.n_frames):
        img.seek(i)
        frames.append(img.convert("RGBA"))
        durations.append(int(img.info.get("duration", 100)) or 100)
    frames[0].save(
        dest,
        "GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
    )


def convert_single(source, dest, target_format, quality=90,
                   max_edge=None, scale_percent=None):
    """转换单个图片文件。

    参数:
        max_edge      最长边像素上限（超过时等比缩小，不会放大）
        scale_percent 等比缩放百分比（1-99，<100 时生效）
        quality       JPEG/WEBP 质量 1-100

    说明:
        - 自动按 EXIF 方向旋转手机竖拍照片，避免输出 90° 歪斜
        - 目标为 JPEG 且原图含透明通道时，以白色背景合成，避免透明变黑
        - 目标为 GIF 且源为动态 GIF 时保留全部帧
        - 源为动态 GIF 且目标非 GIF 时，取第一帧
    """
    fmt = FORMAT_ALIASES.get(str(target_format).upper())
    if fmt is None:
        raise ValueError(f"不支持的目标格式: {target_format}")

    source, dest = Path(source), Path(dest)
    if not source.is_file():
        raise FileNotFoundError(str(source))
    dest.parent.mkdir(parents=True, exist_ok=True)

    img = Image.open(source)  # 可能抛出 UnidentifiedImageError
    try:
        # 1) EXIF 方向修正
        if _exif_needs_transpose(img):
            img = ImageOps.exif_transpose(img)
            img.info.pop("exif", None)  # 防止保存后查看器再次旋转

        # 2) 缩放（取两个约束中最小的比例，只缩不放）
        factor = 1.0
        w, h = img.size
        if max_edge and max(w, h) > int(max_edge):
            factor = min(factor, int(max_edge) / max(w, h))
        if scale_percent is not None and 0 < int(scale_percent) < 100:
            factor = min(factor, int(scale_percent) / 100)
        if factor < 1:
            img = img.resize(
                (max(1, round(w * factor)), max(1, round(h * factor))),
                Image.LANCZOS,
            )

        # 3) 动态 GIF → GIF：保留全部帧
        if fmt == "GIF" and getattr(img, "n_frames", 1) > 1:
            _save_gif_all_frames(img, dest)
            return True

        # 4) 透明通道处理
        if fmt == "JPEG":
            has_alpha = img.mode in ("RGBA", "LA", "PA") or (
                img.mode == "P" and "transparency" in img.info
            )
            if has_alpha:
                rgba = img.convert("RGBA")
                background = Image.new("RGB", rgba.size, (255, 255, 255))
                background.paste(rgba, mask=rgba.split()[3])
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")
        elif img.mode == "P" and img.info.get("transparency") is not None:
            img = img.convert("RGBA")

        img.save(dest, fmt, **_save_quality_args(fmt, quality))
    finally:
        img.close()
    return True


# ------------------------------------------------------------------ 批量

def batch_convert(
    input_folder,
    output_folder,
    target_format,
    quality=90,
    recursive=True,
    progress_cb=None,
    log_cb=None,
    cancel_event=None,
    max_edge=None,
    scale_percent=None,
):
    """批量转换 input_folder 下的所有图片到 output_folder。

    回调签名:
        progress_cb(done, total, name)
        log_cb(name, ok: bool, message: str)
    cancel_event: 可选 threading.Event，set() 后跳过剩余文件。
    返回 ConversionStats。
    """
    stats = ConversionStats()
    files = find_image_files(input_folder, recursive=recursive)
    stats.total = len(files)
    root_in, root_out = Path(input_folder), Path(output_folder)
    # JPEG 目标使用更符合惯例的 .jpg 扩展名
    out_ext = "jpg" if str(target_format).upper() in ("JPEG", "JPG") else str(target_format).lower()

    processed = 0
    for src in files:
        if cancel_event is not None and cancel_event.is_set():
            stats.cancelled = len(files) - processed
            break

        rel = src.relative_to(root_in)
        dest = root_out / rel.with_suffix("." + out_ext)
        try:
            convert_single(
                src, dest, target_format,
                quality=quality, max_edge=max_edge, scale_percent=scale_percent,
            )
            stats.success += 1
            stats.bytes_in += src.stat().st_size
            stats.bytes_out += dest.stat().st_size
            if log_cb:
                log_cb(str(rel), True, "转换成功")
        except Exception as exc:  # noqa: BLE001 - 单文件失败不中断整批
            stats.failed += 1
            stats.errors.append((str(rel), str(exc)))
            if log_cb:
                log_cb(str(rel), False, str(exc))

        processed += 1
        if progress_cb:
            progress_cb(processed, stats.total, str(rel))
    return stats


# ------------------------------------------------------------------ CLI

def cli(argv=None):
    """命令行模式：python app.py <输入> <输出> -f JPEG [--quality 90] …

    退出码：0 全部成功；1 存在失败文件；2 参数/格式错误。
    """
    parser = argparse.ArgumentParser(
        prog="image-format-tool",
        description="批量图片格式转换工具（CLI 模式；不带参数时启动图形界面）",
    )
    parser.add_argument("input", help="输入文件夹或单个图片文件")
    parser.add_argument("output", help="输出文件夹")
    parser.add_argument("-f", "--format", dest="target_format", default="JPEG",
                        help="目标格式 PNG/JPEG/BMP/GIF/TIFF/WEBP（大小写不敏感，默认 JPEG）")
    parser.add_argument("-q", "--quality", type=int, default=90,
                        help="质量 1-100（默认 90）")
    parser.add_argument("--no-recursive", dest="recursive", action="store_false",
                        default=True, help="不处理子目录")
    parser.add_argument("--max-edge", type=int, default=None,
                        help="最长边像素上限（只缩不放）")
    parser.add_argument("--scale", type=int, default=None,
                        help="缩放百分比 1-99")
    args = parser.parse_args(argv)

    fmt = args.target_format.upper()
    if fmt not in FORMAT_ALIASES:
        parser.error(
            f"不支持的目标格式：{args.target_format}"
            f"（可选：{'/'.join(sorted(FORMAT_ALIASES))}）")

    inp, outp = Path(args.input), Path(args.output)
    outp.mkdir(parents=True, exist_ok=True)
    out_ext = "jpg" if fmt in ("JPEG", "JPG") else fmt.lower()

    if inp.is_file():
        dest = outp / (inp.stem + "." + out_ext)
        try:
            convert_single(inp, dest, fmt, quality=args.quality,
                           max_edge=args.max_edge, scale_percent=args.scale)
        except Exception as exc:  # noqa: BLE001
            print(f"❌ {inp.name}: {exc}")
            return 1
        print(f"✅ {inp.name} → {dest}")
        return 0

    def _progress(done, total, name):
        print(f"[{done}/{total}] {name}")

    stats = batch_convert(
        inp, outp, fmt,
        quality=args.quality, recursive=args.recursive,
        progress_cb=_progress, max_edge=args.max_edge, scale_percent=args.scale,
    )
    print(f"\n完成：成功 {stats.success}，失败 {stats.failed}，"
          f"取消 {stats.cancelled}，共 {stats.total} 个文件")
    if stats.savings_pct is not None:
        direction = "减小" if stats.savings_pct >= 0 else "增大"
        print(f"体积{direction} {abs(stats.savings_pct)}%")
    for name, msg in stats.errors:
        print(f"  ❌ {name}: {msg}")
    return 0 if stats.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(cli())

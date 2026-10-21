"""converter 模块的单元测试（不依赖 GUI / 网络）。

运行方式：
    python -m unittest discover -s tests -v
或
    pytest -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# 允许从项目根目录运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

import converter
from converter import (
    FORMAT_ALIASES,
    batch_convert,
    convert_single,
    find_image_files,
)


def make_image(path: Path, mode="RGB", size=(32, 32)):
    """生成一张真实的图片文件。"""
    img = Image.new(mode, size)
    # 画几块彩色像素，使内容不为全 0，方便校验
    if mode in ("RGB", "RGBA"):
        img.paste((255, 0, 0), (0, 0, 1, 1))
        img.paste((0, 255, 0), (16, 16, 17, 17))
    img.save(path)
    return path


class TestFindImageFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_image(self.root / "a.png")
        make_image(self.root / "photo.jpg")
        (self.root / "sub").mkdir()
        make_image(self.root / "sub" / "nested.png")
        (self.root / "notes.txt").write_text("not an image")

    def tearDown(self):
        self.tmp.cleanup()

    def test_recursive_finds_all(self):
        files = find_image_files(self.root, recursive=True)
        names = {f.name for f in files}
        self.assertEqual(names, {"a.png", "photo.jpg", "nested.png"})

    def test_flat_only(self):
        files = find_image_files(self.root, recursive=False)
        names = {f.name for f in files}
        self.assertEqual(names, {"a.png", "photo.jpg"})

    def test_missing_folder_returns_empty(self):
        self.assertEqual(find_image_files(self.root / "nope"), [])

    def test_ignores_non_images(self):
        self.assertFalse(any(f.suffix == ".txt" for f in find_image_files(self.root)))


class TestConvertSingle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_png_to_jpeg(self):
        src = make_image(self.root / "src.png")
        dst = self.root / "out" / "src.jpg"
        self.assertTrue(convert_single(src, dst, "JPEG"))
        self.assertTrue(dst.is_file())
        with Image.open(dst) as img:
            self.assertEqual(img.format, "JPEG")

    def test_transparent_png_to_jpeg_uses_white_background(self):
        src = self.root / "tr.png"
        Image.new("RGBA", (32, 32), (0, 0, 0, 0)).save(src)
        dst = self.root / "tr.jpg"
        convert_single(src, dst, "JPEG")
        with Image.open(dst) as img:
            self.assertEqual(img.mode, "RGB")
            # 全透明角落应变为白色，而非黑色
            px = img.convert("RGB").getpixel((0, 0))
            self.assertGreaterEqual(sum(px) / 3, 200)

    def test_palette_mode_conversion(self):
        src = self.root / "pal.gif"
        Image.new("P", (16, 16)).save(src)
        dst = self.root / "pal.png"
        convert_single(src, dst, "PNG")
        with Image.open(dst) as img:
            self.assertEqual(img.format, "PNG")

    def test_quality_clamped(self):
        src = make_image(self.root / "s.png")
        dst = self.root / "q.jpg"
        convert_single(src, dst, "JPEG", quality=10_000)  # 超过上限
        self.assertTrue(dst.is_file())
        convert_single(self.root / "s.png", self.root / "q2.jpg", "JPEG", quality=-5)
        self.assertTrue((self.root / "q2.jpg").is_file())

    def test_unsupported_format_raises(self):
        src = make_image(self.root / "s.png")
        with self.assertRaises(ValueError):
            convert_single(src, self.root / "x.avif", "AVIF")

    def test_missing_source_raises(self):
        with self.assertRaises(FileNotFoundError):
            convert_single(self.root / "ghost.png", self.root / "o.png", "PNG")

    def test_corrupt_file_raises(self):
        bad = self.root / "bad.png"
        bad.write_bytes(b"this is not an image at all")
        with self.assertRaises(Exception):
            convert_single(bad, self.root / "o.png", "PNG")


class TestBatchConvert(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.inp = Path(self.tmp.name) / "in"
        self.out = Path(self.tmp.name) / "out"
        self.inp.mkdir()
        make_image(self.inp / "a.png")
        make_image(self.inp / "b.jpg")
        (self.inp / "sub").mkdir()
        make_image(self.inp / "sub" / "c.png")
        (self.inp / "bad.png").write_bytes(b"corrupt")

    def tearDown(self):
        self.tmp.cleanup()

    def test_stats_counts(self):
        stats = batch_convert(self.inp, self.out, "PNG", recursive=True)
        self.assertEqual(stats.total, 4)
        self.assertEqual(stats.success, 3)
        self.assertEqual(stats.failed, 1)
        self.assertTrue(stats.finished)
        # 嵌套结构被保留
        self.assertTrue((self.out / "sub" / "c.png").is_file())

    def test_progress_and_log_callbacks(self):
        progress_calls, log_calls = [], []
        batch_convert(
            self.inp,
            self.out,
            "JPEG",
            progress_cb=lambda d, t, n: progress_calls.append((d, t)),
            log_cb=lambda n, ok, m: log_calls.append((n, ok)),
        )
        self.assertEqual(len(progress_calls), 4)
        self.assertEqual(progress_calls[-1][0], 4)
        self.assertEqual(len(log_calls), 4)
        self.assertEqual(sum(1 for _, ok in log_calls if ok), 3)

    def test_empty_folder(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        stats = batch_convert(empty, self.out, "PNG")
        self.assertEqual(stats.total, 0)
        self.assertEqual(stats.success, 0)
        self.assertFalse(stats.finished)


class TestFormatAliases(unittest.TestCase):
    def test_jpg_maps_to_jpeg(self):
        self.assertEqual(FORMAT_ALIASES["JPG"], "JPEG")

    def test_all_supported_formats_in_aliases(self):
        for ext in converter.IMAGE_EXTENSIONS:
            base = ext.lstrip(".").upper()
            self.assertIn(base, FORMAT_ALIASES or {})


# ---------------------------------------------------------------- 新增功能测试


def make_exif_jpeg(path: Path, orientation: int = 6):
    """创建带 EXIF 方向标记的竖图（20x40，orientation=6 表示需顺时针 90°）。"""
    img = Image.new("RGB", (20, 40), (0, 0, 0))
    exif = img.getexif()
    exif[0x0112] = orientation
    img.save(path, exif=exif.tobytes())
    return path


class TestExifOrientation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_orientation_6_rotates_image(self):
        # 20x40 竖图 + orientation=6 → 输出应为 40x20
        src = make_exif_jpeg(self.root / "phone.jpg", orientation=6)
        dst = self.root / "phone.png"
        convert_single(src, dst, "PNG")
        with Image.open(dst) as img:
            self.assertEqual(img.size, (40, 20))
            # 修正后 EXIF 方向不应残留为 6
            self.assertEqual(img.getexif().get(0x0112, 1), 1)

    def test_no_orientation_keeps_size(self):
        src = make_image(self.root / "plain.jpg")
        dst = self.root / "plain.png"
        convert_single(src, dst, "PNG")
        with Image.open(dst) as img:
            self.assertEqual(img.size, (32, 32))


class TestScaling(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_max_edge_downscales(self):
        src = make_image(self.root / "big.png", size=(200, 100))
        dst = self.root / "big.jpg"
        convert_single(src, dst, "JPEG", max_edge=50)
        with Image.open(dst) as img:
            self.assertEqual(img.size, (50, 25))

    def test_max_edge_no_upscale(self):
        src = make_image(self.root / "small.png", size=(10, 10))
        dst = self.root / "small.jpg"
        convert_single(src, dst, "JPEG", max_edge=100)
        with Image.open(dst) as img:
            self.assertEqual(img.size, (10, 10))

    def test_scale_percent(self):
        src = make_image(self.root / "s.png", size=(200, 100))
        dst = self.root / "s50.jpg"
        convert_single(src, dst, "JPEG", scale_percent=50)
        with Image.open(dst) as img:
            self.assertEqual(img.size, (100, 50))

    def test_scale_and_max_edge_combined(self):
        src = make_image(self.root / "c.png", size=(400, 400))
        dst = self.root / "c.jpg"
        # 50% → 200x200，再受 max_edge=80 约束 → 80x80
        convert_single(src, dst, "JPEG", scale_percent=50, max_edge=80)
        with Image.open(dst) as img:
            self.assertEqual(img.size, (80, 80))


class TestDynamicGif(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.frames = [
            Image.new("RGBA", (8, 8), (255, 0, 0, 255)),
            Image.new("RGBA", (8, 8), (0, 255, 0, 255)),
            Image.new("RGBA", (8, 8), (0, 0, 255, 255)),
        ]
        self.frames[0].save(
            self.root / "anim.gif", save_all=True,
            append_images=self.frames[1:], duration=50, loop=0)

    def tearDown(self):
        self.tmp.cleanup()

    def test_gif_to_gif_keeps_all_frames(self):
        dst = self.root / "anim_out.gif"
        convert_single(self.root / "anim.gif", dst, "GIF")
        with Image.open(dst) as img:
            self.assertEqual(img.n_frames, 3)

    def test_dynamic_gif_to_png_uses_first_frame(self):
        dst = self.root / "first.png"
        convert_single(self.root / "anim.gif", dst, "PNG")
        with Image.open(dst) as img:
            self.assertEqual(img.n_frames, 1)
            self.assertGreater(img.convert("RGB").getpixel((0, 0))[0], 200)  # 第一帧为红色


class TestCancelAndStats(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.inp = Path(self.tmp.name) / "in"
        self.out = Path(self.tmp.name) / "out"
        self.inp.mkdir()
        for i in range(5):
            make_image(self.inp / f"img{i}.png")

    def tearDown(self):
        self.tmp.cleanup()

    def test_cancel_event_skips_all(self):
        import threading
        ev = threading.Event()
        ev.set()
        stats = batch_convert(self.inp, self.out, "PNG", cancel_event=ev)
        self.assertEqual(stats.success, 0)
        self.assertEqual(stats.cancelled, 5)
        self.assertTrue(stats.finished)

    def test_bytes_stats_and_savings(self):
        stats = batch_convert(self.inp, self.out, "JPEG", quality=60)
        self.assertEqual(stats.success, 5)
        self.assertGreater(stats.bytes_in, 0)
        self.assertGreater(stats.bytes_out, 0)
        self.assertIsInstance(stats.savings_pct, float)

    def test_savings_none_when_no_input_bytes(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        stats = batch_convert(empty, self.out, "PNG")
        self.assertIsNone(stats.savings_pct)


class TestAppHelpers(unittest.TestCase):
    """GUI 层的纯函数与设置记忆（不创建窗口）。"""

    def test_parse_scale_option(self):
        from app import parse_scale_option
        self.assertIsNone(parse_scale_option("保持原尺寸"))
        self.assertEqual(parse_scale_option("90%"), 90)
        self.assertEqual(parse_scale_option("50%"), 50)
        self.assertIsNone(parse_scale_option("100%"))   # 越界视为不缩放
        self.assertIsNone(parse_scale_option("abc"))

    def test_human_size(self):
        from app import human_size
        self.assertEqual(human_size(0), "0 B")
        self.assertEqual(human_size(1024), "1.0 KB")
        self.assertEqual(human_size(10 * 1024 * 1024), "10.0 MB")

    def test_settings_roundtrip(self):
        import app
        original = app.SETTINGS_FILE
        try:
            fake = Path(tempfile.gettempdir()) / f"ift_settings_{os.getpid()}.json"
            app.SETTINGS_FILE = str(fake)
            app.save_settings({"input_folder": "/tmp/a", "format": "PNG",
                              "quality": 80, "recursive": False, "scale": "75%"})
            data = app.load_settings()
            self.assertEqual(data["format"], "PNG")
            self.assertEqual(data["quality"], 80)
            self.assertFalse(data["recursive"])
        finally:
            app.SETTINGS_FILE = original
            if os.path.exists(str(fake)):
                os.remove(str(fake))

    def test_load_settings_missing_file(self):
        import app
        original = app.SETTINGS_FILE
        try:
            app.SETTINGS_FILE = os.path.join(tempfile.gettempdir(), "definitely_not_exist_9x.json")
            self.assertEqual(app.load_settings(), {})
        finally:
            app.SETTINGS_FILE = original


class TestCli(unittest.TestCase):
    def _run_cli(self, *args):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = converter.cli([str(a) for a in args])
        return code, buf.getvalue()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.inp = Path(self.tmp.name) / "in"
        self.out = Path(self.tmp.name) / "out"
        self.inp.mkdir()
        make_image(self.inp / "a.png")

    def tearDown(self):
        self.tmp.cleanup()

    def test_folder_batch_cli(self):
        code, out = self._run_cli(self.inp, self.out, "-f", "jpeg", "-q", "80")
        self.assertEqual(code, 0)
        self.assertIn("成功 1", out)
        self.assertTrue((self.out / "a.jpg").is_file())

    def test_single_file_cli(self):
        code, _ = self._run_cli(self.inp / "a.png", self.out, "-f", "webp")
        self.assertEqual(code, 0)
        self.assertTrue((self.out / "a.webp").is_file())

    def test_corrupt_file_returns_nonzero(self):
        (self.inp / "bad.png").write_bytes(b"not an image")
        code, out = self._run_cli(self.inp, self.out, "-f", "png")
        self.assertEqual(code, 1)
        self.assertIn("bad.png", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)

# image-format-tool

批量图片格式转换工具（Python + Tkinter + Pillow），支持 GUI 与命令行两种使用方式。

## 功能特性

- 支持 **PNG / JPEG / BMP / GIF / TIFF / WEBP** 互转
- **自动修正 EXIF 方向**：手机竖拍照片不会 90° 歪斜
- **透明 PNG 转 JPEG**：自动以白色背景合成，透明区域不再变黑
- **尺寸缩放**：等比缩小（可选百分比 / 最长边限制），支持批量缩图压缩
- **动态 GIF 保留全部帧**；GIF 转其他格式时取第一帧
- **质量参数**：JPEG/WEBP 可调 1–100，TIFF 启用 LZW 压缩
- **递归处理子目录**，输出保持原目录结构
- **可取消**：转换中途随时停止
- **体积统计**：完成后显示总体积变化（减小/增大百分比）
- **设置记忆**：记住上次的输入/输出文件夹、格式、质量等
- **多线程 + 进度条 + 彩色日志**，单文件失败不中断整批
- **CLI 模式**：脚本化 / 自动化 / 服务器场景

## 目录结构

```
app.py          # GUI 界面层（Tkinter），带参数时进入 CLI 模式
converter.py    # 核心转换逻辑 + CLI（与界面解耦）
tests/          # 单元测试（unittest，34 个用例）
```

## 安装依赖

要求 Python 3.8+（tkinter 为 Python 自带模块，Windows/macOS 默认已包含）。

```shell
pip install -r requirements.txt
```

## 运行 GUI

```shell
python app.py
```

## 运行 CLI

```shell
# 批量转换整个文件夹为 JPEG（质量 85，缩小到 50%）
python app.py <输入文件夹> <输出文件夹> -f jpeg -q 85 --scale 50

# 单张图片转 WebP
python app.py photo.png <输出文件夹> -f webp

# 限制最长边 1920px（只缩不放），不处理子目录
python app.py <输入文件夹> <输出文件夹> -f png --max-edge 1920 --no-recursive
```

常用参数：

| 参数 | 说明 | 默认 |
|---|---|---|
| `input` / `output` | 输入（文件夹或单图）/ 输出文件夹 | 必填 |
| `-f, --format` | 目标格式（大小写不敏感） | `JPEG` |
| `-q, --quality` | 质量 1–100（JPEG/WEBP） | `90` |
| `--scale` | 等比缩小百分比 1–99 | 无 |
| `--max-edge` | 最长边像素上限（只缩不放） | 无 |
| `--no-recursive` | 不处理子目录 | 处理 |

退出码：`0` 全部成功，`1` 存在失败文件，`2` 参数/格式错误。

## 运行测试

```shell
python -m unittest discover -s tests -v
# 或使用 pytest
pytest -v
```

## 说明

- 设置记忆文件位于 `~/.image_format_tool.json`，可手动删除以重置。
- 体积统计基于输入/输出文件字节总和，用于直观判断压缩效果。

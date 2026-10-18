# MiniMax H3 视频工作流

- **笔记本**：[MiniMaxH3.ipynb](../../notebooks/minimax-h3/MiniMaxH3.ipynb)
- **支持显卡**：A100 (80GB)、H100 (80GB)、RTX 6000 (96GB)
- **默认配置**：INT8 ConvRot（主模型 / 文本编码器 / 视频 VAE）、20 步、0.98 MP、5 秒、8-bit H.264 MP4（CRF 18）

| 工作流 | 功能 | 输入要求 | 视频比例 |
| --- | --- | --- | --- |
| [01 · 文生视频](01_MiniMaxH3_T2V.json) | 文生视频 | 提示词 | 手动选择 |
| [02 · 首帧图生视频](02_MiniMaxH3_I2V.json) | 首帧图生视频 | 上传首帧 + 提示词 | 自动跟随首帧 |
| [03 · 首尾帧视频](03_MiniMaxH3_FirstLast.json) | 首尾帧视频 | 上传首帧、尾帧 + 提示词 | 自动跟随首帧 |
| [04 · 双图参考视频](04_MiniMaxH3_R2V.json) | 双图参考视频 | 上传参考图 1、2 + 提示词（`<Picture 1>` / `<Picture 2>`） | 自动跟随参考图 1 |

## 使用说明

1. 按笔记本 `1 → 2 → 3 → 4` 顺序运行，通过 Cloudflare Tunnel 自有域名或 Colab 代理链接打开 ComfyUI。
2. `01–03` 使用 `DOWNLOAD_FL2VA`（默认开启）；`04` 需开启 `DOWNLOAD_R2V` 并重跑第 3 步。
3. 在 ComfyUI 工作流列表打开 `01–04`，上传所需参考图片、填写提示词后运行。

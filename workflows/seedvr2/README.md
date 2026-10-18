# SeedVR2（视频与图片 4K 超分修复工作流）

- **笔记本**：[SeedVR2.ipynb](../../notebooks/seedvr2/SeedVR2.ipynb)
- **支持显卡**：A100 (40GB / 80GB)、H100 (80GB)、RTX 6000 (96GB)
- **默认配置**：字节跳动 `SeedVR2` 原生 FP16 全精度（`seedvr2_7b_sharp_fp16` 15.35GB 旗舰锐化版 + `seedvr2_3b_fp16` 6.32GB 长视频极速版 + `seedvr2_ema_vae_fp16` 0.47GB，合计约 22.1 GB）、**1 步扩散极速修复**、视频超分自动保留原视频声音与帧率

| 工作流 | 功能 | 输入要求 | 默认放大倍数 |
| --- | --- | --- | --- |
| [01 · 视频超分修复 (7B Sharp)](01_SeedVR2_Video_Upscale_7B_Sharp.json) | 旗舰 7B Sharp 视频画质修复与放大（保留原音频） | 上传视频（如 MiniMax H3 生成的 720p 视频） | `2x`（可改 `4x` 4K） |
| [02 · 长视频极速超分 (3B Fast)](02_SeedVR2_Video_Upscale_3B_Fast.json) | 3B 极速长视频分块超分（默认开启 `Split Latent`） | 上传较长视频片段 | `2x`（可改 `4x` 4K） |
| [03 · 图片 4K 超分与对比 (7B Sharp)](03_SeedVR2_Image_Upscale_7B_Sharp.json) | 单图 4 倍 4K 细节重绘 + 交互式滑块前后对比 | 上传图片（如 1K 生图或老照片） | `4x`（1024 → 4096） |

## 使用说明

1. 按笔记本 `1 → 2 → 3 → 4` 顺序运行，通过 Cloudflare Tunnel 自有域名打开 ComfyUI。
2. 第 3 步默认一并下载 `7B Sharp FP16` 与 `3B FP16` 两套全精度权重，`01–03` 工作流均可直接运行。
3. 若放大较长视频或开启 `4x` 超分，建议在工作流节点中开启 `长视频分段显存优化 (Split Latent)` 以避免显存峰值溢出。


# Qwen-Image 2.1 工作流

- **笔记本**：[Qwen_Image_2.1_A100_80GB.ipynb](../../notebooks/qwen-image-2.1/Qwen_Image_2.1_A100_80GB.ipynb)
- **默认配置**：BF16（主模型 / 文本编码器 / VAE）、2K 分辨率（可切换 1K / 原图）、40 步、单张、种子 42

| 工作流 | 功能 | 输入要求 | LoRA |
| --- | --- | --- | --- |
| [01 · 文生图](01_Qwen_Image_2_1_T2I_A100.json) | 基础文生图 | 提示词 | 无需 |
| [02 · 单图编辑](02_Qwen_Image_2_1_Reference_A100.json) | 单图编辑 | 上传 1 张图片 + `<image1>` 指令 | 无需 |
| [03 · LoRA 文生图](03_Qwen_Image_2_1_T2I_LoRA_A100.json) | 动漫一致性文生图 | 动漫提示词 | `Qwen2.1_Anime_consistency.safetensors` |
| [04 · LoRA 单图编辑](04_Qwen_Image_2_1_Reference_LoRA_A100.json) | 动漫一致性单图编辑 | 上传 1 张图片 + `<image1>` 指令 | `Qwen2.1_Anime_consistency.safetensors` |
| [05 · 双图编辑](05_Qwen_Image_2_1_Two_Images_A100.json) | 双图合成编辑 | 上传 2 张图片 + `<image1>` / `<image2>` 指令 | 无需 |

## 使用说明

1. 按笔记本 `1 → 2 → 3 → 4` 顺序运行，点击链接打开 ComfyUI。
2. 第 3 步默认一并下载 `Qwen2.1_Anime_consistency.safetensors`（约 168 MB），`01–05` 工作流均可直接使用。
3. 在 ComfyUI 工作流列表打开 `01–05`，按需上传参考图并填写提示词后运行。

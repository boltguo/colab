# Qwen-Image 2.1 Uncensored 工作流

- **笔记本**：[Qwen_Image_2.1_Uncensored_A100_40GB.ipynb](../../notebooks/qwen-image-2.1-uncensored/Qwen_Image_2.1_Uncensored_A100_40GB.ipynb)
- **默认配置**：BF16 GGUF 主模型 + INT8 文本编码器 + BF16 VAE、2K 分辨率（可切换 1K）、40 步、单张、无需 LoRA

| 工作流 | 功能 | 输入要求 |
| --- | --- | --- |
| [01 · 文字生图](01_Qwen_Image_2_1_Uncensored_T2I_A100.json) | 文字生图 | 提示词 |
| [02 · 图片编辑](02_Qwen_Image_2_1_Uncensored_Reference_A100.json) | 单图编辑 | 上传 1 张图片 + 编辑指令 |
| [03 · 双图编辑](03_Qwen_Image_2_1_Uncensored_Two_Images_A100.json) | 双图编辑 | 上传 2 张图片 + 编辑指令 |

## 使用说明

1. 按笔记本 `1 → 2 → 3 → 4` 顺序运行，点击链接打开 ComfyUI。
2. 显存紧张时可在第 3 步切换 `Q8_0` 主模型或 `1K` 分辨率；切换精度重跑第 3 步后需重新打开工作流。
3. 在 ComfyUI 工作流列表打开 `01–03`，上传所需图片并填写编辑指令后运行。

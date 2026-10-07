# Qwen-Image 2.1 工作流

| 文件 | 用途 |
| --- | --- |
| [01 · 文生图](01_Qwen_Image_2_1_T2I_A100.json) | 基础版 |
| [02 · 参考图](02_Qwen_Image_2_1_Reference_A100.json) | 图片编辑 |
| [03 · LoRA 文生图](03_Qwen_Image_2_1_T2I_LoRA_A100.json) | 动漫一致性 LoRA |
| [04 · LoRA 参考图](04_Qwen_Image_2_1_Reference_LoRA_A100.json) | 动漫一致性 LoRA |

1. 打开 [A100 笔记本](../../notebooks/qwen-image-2.1/Qwen_Image_2.1_A100_80GB.ipynb)，依次运行环境、模型与工作流、启动三格。
2. 点击新窗口链接，打开对应工作流。修改提示词；参考版先上传图片，再点击运行。
3. 生成后运行第 4 格，下载单张图片与内嵌工作流，或下载全部图片。重跑下载格刷新列表。

工作流默认下载 `main` 分支，同名直接覆盖；网络或 JSON 错误保留已有文件。

默认 **2K、40 步、单张、种子 42**。文生图下拉选择 **1K / 2K** 和画面比例；参考版可选 **1K / 2K / 原图**，保留图片比例。尺寸按 32 的倍数取整。控件和子图均为 ComfyUI 内置，无需额外节点包。

使用 03/04 前，在第 2 格勾选 LoRA 下载，或将 `Qwen2.1_Anime_consistency.safetensors` 放入 `models/loras/`。默认强度 1.0；权重来源：[WarmBloodAban](https://huggingface.co/WarmBloodAban/Qwen-Image-2.1-LoRAs)。

PNG 位于 `/content/ComfyUI/output/qwen-image-2.1/`，默认内嵌工作流，可再次拖入 ComfyUI。参考图片需单独保留。

模型来源：[Comfy-Org/Qwen-Image-2.1](https://huggingface.co/Comfy-Org/Qwen-Image-2.1)。Built with Qwen；遵循[模型许可](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE)。

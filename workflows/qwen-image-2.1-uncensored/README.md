# Qwen-Image 2.1 Uncensored

[Notebook · A100 40GB / 80GB](../../notebooks/qwen-image-2.1-uncensored/Qwen_Image_2.1_Uncensored_A100_40GB.ipynb)

| 工作流 | 输入 |
| --- | --- |
| [01 · 文字生图](01_Qwen_Image_2_1_Uncensored_T2I_A100.json) | 提示词 |
| [02 · 图片编辑](02_Qwen_Image_2_1_Uncensored_Reference_A100.json) | 上传图片 + 编辑指令 |

依次运行 notebook 四格，打开 ComfyUI，选择 01 或 02。无需 LoRA。

默认 **BF16 主模型 + INT8 文本编码器 + BF16 VAE；2K、40 步、单张**。第 2 格可切换 Q8_0 或 BF16 文本编码器；切换后重新打开工作流。显存不足时先选 1K。

第 2 格从 GitHub 下载两个工作流，默认 `main`。同名覆盖；下载失败保留已有文件。

图片保存在 `/content/ComfyUI/output/qwen-image-2.1-uncensored/`，第 4 格下载图片与内嵌工作流。

[模型来源](https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-GGUF) · [GGUF 节点](https://github.com/leejet/ComfyUI-GGUF) · [模型许可](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE)。Built with Qwen.

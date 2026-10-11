# A100 模型笔记本

| 模型 | 当前入口 | Colab |
| --- | --- | --- |
| MiniMax H3 · ComfyUI | [视频笔记本](notebooks/minimax-h3/MiniMaxH3_A100_80GB.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/minimax-h3/MiniMaxH3_A100_80GB.ipynb) |
| Qwen-Image-2.1 · ComfyUI | [图片笔记本](notebooks/qwen-image-2.1/Qwen_Image_2.1_A100_80GB.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/qwen-image-2.1/Qwen_Image_2.1_A100_80GB.ipynb) |
| Qwen-Image-2.1 Uncensored GGUF · ComfyUI · A100 40GB/80GB | [GGUF 图片笔记本](notebooks/qwen-image-2.1-uncensored/Qwen_Image_2.1_Uncensored_A100_40GB.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/qwen-image-2.1-uncensored/Qwen_Image_2.1_Uncensored_A100_40GB.ipynb) |

MiniMax H3 和原版 Qwen 笔记本选择 **A100 80GB**；新增的 Uncensored GGUF 笔记本接受 **A100 40GB / 80GB**。依次运行：环境 → 模型与工作流 → 打开 ComfyUI → 下载结果。点击新窗口链接后保持 Colab 连接。

[MiniMax 视频工作流](workflows/minimax-h3/README.md)：文生、首帧、首尾帧、双图参考；04 尚未提供音频或视频上传入口。

[Qwen 图片工作流](workflows/qwen-image-2.1/README.md)：文生、参考图及 LoRA 版本；默认 2K，下拉选择分辨率。

[Qwen Uncensored GGUF 工作流](workflows/qwen-image-2.1-uncensored/README.md)：01 文字生图、02 单图编辑、03 双图编辑；默认 BF16 主模型、INT8 文本编码器、BF16 VAE，无需 LoRA。工作流从 GitHub 下载，支持切换 Q8_0 和 BF16 文本编码器。

代码：[Apache-2.0](LICENSE)。模型及 LoRA 遵循其来源许可证：[MiniMax H3](https://huggingface.co/Comfy-Org/MiniMax-H3)、[Turbo LoRA](https://huggingface.co/lightx2v/Minimax-h3-Turbo)、[Qwen](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE)、[Qwen Uncensored GGUF](https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-GGUF)。Built with Qwen.

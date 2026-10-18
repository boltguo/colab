# A100 ComfyUI 笔记本

| 模型 | 硬件要求 | 笔记本 | 工作流文档 | Colab |
| --- | --- | --- | --- | --- |
| MiniMax H3 | A100 80GB | [MiniMaxH3_A100_80GB.ipynb](notebooks/minimax-h3/MiniMaxH3_A100_80GB.ipynb) | [工作流说明](workflows/minimax-h3/README.md) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/minimax-h3/MiniMaxH3_A100_80GB.ipynb) |
| Qwen-Image 2.1 | A100 80GB | [Qwen_Image_2.1_A100_80GB.ipynb](notebooks/qwen-image-2.1/Qwen_Image_2.1_A100_80GB.ipynb) | [工作流说明](workflows/qwen-image-2.1/README.md) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/qwen-image-2.1/Qwen_Image_2.1_A100_80GB.ipynb) |
| Qwen-Image 2.1 Uncensored GGUF | A100 40GB / 80GB | [Qwen_Image_2.1_Uncensored_A100_40GB.ipynb](notebooks/qwen-image-2.1-uncensored/Qwen_Image_2.1_Uncensored_A100_40GB.ipynb) | [工作流说明](workflows/qwen-image-2.1-uncensored/README.md) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/qwen-image-2.1-uncensored/Qwen_Image_2.1_Uncensored_A100_40GB.ipynb) |

## 统一运行流程

1. **环境检测**：检查 A100 GPU、显存容量、PyTorch 与 CUDA 状态。
2. **安装 ComfyUI**：安装指定版本 ComfyUI 与依赖，初始化本地目录 `/content/ComfyUI`。
3. **下载模型与工作流**：按所选参数下载模型权重至 `models/`，同步工作流至 `user/default/workflows/`。
4. **启动并打开 ComfyUI**：启动 `8188` 端口服务并生成外部浏览器访问链接（使用期间保持 Colab 页面连接）。

## 许可

- 代码：[Apache-2.0](LICENSE)
- 模型权重：[MiniMax H3](https://huggingface.co/Comfy-Org/MiniMax-H3) · [Turbo LoRA](https://huggingface.co/lightx2v/Minimax-h3-Turbo) · [Qwen-Image 2.1](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE) · [Qwen Uncensored GGUF](https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-GGUF)

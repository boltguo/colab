# ComfyUI 模型笔记本

支持 **A100**、**H100**、**RTX 6000 (96GB)** 三款显卡：
- **MiniMax H3** 与 **Qwen-Image 2.1**：需 **80GB 及以上显存**（A100 80GB / H100 80GB / RTX 6000 96GB）。
- **Qwen-Image 2.1 Uncensored GGUF** 与 **IndexTTS 2.5**：**40GB 及以上显存即可**（A100 40GB / 80GB、H100 80GB、RTX 6000 96GB）。

| 模型 | 笔记本 | 工作流文档 | Colab |
| --- | --- | --- | --- |
| MiniMax H3 | [MiniMaxH3.ipynb](notebooks/minimax-h3/MiniMaxH3.ipynb) | [工作流说明](workflows/minimax-h3/README.md) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/minimax-h3/MiniMaxH3.ipynb) |
| Qwen-Image 2.1 | [Qwen_Image_2.1.ipynb](notebooks/qwen-image-2.1/Qwen_Image_2.1.ipynb) | [工作流说明](workflows/qwen-image-2.1/README.md) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/qwen-image-2.1/Qwen_Image_2.1.ipynb) |
| Qwen-Image 2.1 Uncensored GGUF | [Qwen_Image_2.1_Uncensored.ipynb](notebooks/qwen-image-2.1-uncensored/Qwen_Image_2.1_Uncensored.ipynb) | [工作流说明](workflows/qwen-image-2.1-uncensored/README.md) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/qwen-image-2.1-uncensored/Qwen_Image_2.1_Uncensored.ipynb) |
| IndexTTS 2.5 | [IndexTTS_2.5.ipynb](notebooks/indextts-2.5/IndexTTS_2.5.ipynb) | [工作流说明](workflows/indextts-2.5/README.md) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/indextts-2.5/IndexTTS_2.5.ipynb) |

## 统一运行流程

1. **环境检测**：检测 GPU 型号（A100 / H100 / RTX 6000）、显存容量、BF16 与 CUDA 状态。
2. **安装 ComfyUI**：安装指定版本 ComfyUI、依赖与 `cloudflared`，初始化本地目录 `/content/ComfyUI`。
3. **下载模型与工作流**：自动读取 Colab Secrets 中的 `HF_TOKEN`（可选），下载模型权重至 `models/`，同步工作流至 `user/default/workflows/`。
4. **启动并打开 ComfyUI**：启动 `8188` 端口服务；自动从 Colab 左侧 **🔑 Secrets（密钥）** 读取 `CF_TUNNEL_TOKEN` 挂载至自有域名（保存一次长期有效，无需每次输入）。

## 许可

- 代码：[Apache-2.0](LICENSE)
- 模型权重：[MiniMax H3](https://huggingface.co/Comfy-Org/MiniMax-H3) · [Turbo LoRA](https://huggingface.co/lightx2v/Minimax-h3-Turbo) · [Qwen-Image 2.1](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE) · [Qwen Uncensored GGUF](https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-GGUF) · [IndexTTS-2.5](https://huggingface.co/IndexTeam/IndexTTS-2.5)

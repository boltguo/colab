# ComfyUI 模型笔记本

支持 **A100**、**H100**、**RTX 6000 (96GB)** 三款显卡：
- **MiniMax H3**、**Qwen-Image 2.1** 与 **Qwen3.8-27B（BF16）**：需 **80GB 及以上显存**（A100 80GB / H100 80GB / RTX 6000 96GB）。
- **Krea 2（BF16）**、**SeedVR2（FP16）**、**IndexTTS 2.5** 与 **Qwen3.8-27B（FP8）**：**40GB 及以上显存即可**（A100 40GB / 80GB、H100 80GB、RTX 6000 96GB）。

| 模型 | 笔记本 | Colab |
| --- | --- | --- |
| MiniMax H3 | [MiniMaxH3.ipynb](notebooks/minimax-h3/MiniMaxH3.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/minimax-h3/MiniMaxH3.ipynb) |
| Qwen-Image 2.1 | [Qwen_Image_2.1.ipynb](notebooks/qwen-image-2.1/Qwen_Image_2.1.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/qwen-image-2.1/Qwen_Image_2.1.ipynb) |
| Krea 2 | [Krea_2.ipynb](notebooks/krea-2/Krea_2.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/krea-2/Krea_2.ipynb) |
| SeedVR2 | [SeedVR2.ipynb](notebooks/seedvr2/SeedVR2.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/seedvr2/SeedVR2.ipynb) |
| IndexTTS 2.5 | [IndexTTS_2.5.ipynb](notebooks/indextts-2.5/IndexTTS_2.5.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/indextts-2.5/IndexTTS_2.5.ipynb) |
| Qwen3.8-27B | [Qwen3.8_27B.ipynb](notebooks/qwen3.8-27b/Qwen3.8_27B.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/qwen3.8-27b/Qwen3.8_27B.ipynb) |

## 统一运行流程

1. **环境检测**：检测 GPU 型号（A100 / H100 / RTX 6000）、显存容量、BF16 与 CUDA 状态。
2. **安装服务环境**：安装 ComfyUI `v0.43.2`（或 vLLM `0.32.0`）、依赖与 `cloudflared` `2026.10.6`。
3. **下载模型与工作流**：下载全部模型权重并同步工作流。
4. **启动并挂载服务**：启动 `8188` 端口服务，从 Colab 左侧 **🔑 Secrets** 读取 `CF_TUNNEL_TOKEN` 挂载至自有域名。

## 许可

- 代码：[Apache-2.0](LICENSE)
- 模型权重：[MiniMax H3](https://huggingface.co/Comfy-Org/MiniMax-H3) · [Turbo LoRA](https://huggingface.co/lightx2v/Minimax-h3-Turbo) · [Qwen-Image 2.1](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE) · [Krea 2](https://huggingface.co/Comfy-Org/Krea-2) · [SeedVR2](https://huggingface.co/Comfy-Org/SeedVR2) · [IndexTTS-2.5](https://huggingface.co/IndexTeam/IndexTTS-2.5) · [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B)

# ComfyUI 模型笔记本

支持 **A100**、**H100**、**RTX 6000 (96GB)** 三款显卡：
- **MiniMax H3**、**Qwen-Image 2.1** 与 **Qwen3.8-27B（BF16）**：需 **80GB 及以上显存**（A100 80GB / H100 80GB / RTX 6000 96GB）。
- **Krea 2（BF16）**、**SeedVR2（FP16）**、**IndexTTS 2.5** 与 **Qwen3.8-27B（FP8）**：**40GB 及以上显存即可**（A100 40GB / 80GB、H100 80GB、RTX 6000 96GB）。

| 模型 | 笔记本 | Colab |
| --- | --- | --- |
| MiniMax H3 | [MiniMaxH3.ipynb](notebooks/minimax-h3/MiniMaxH3.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/minimax-h3/MiniMaxH3.ipynb) |
| H3 V1.5 人物替换（96GB） | [H3_Character_Swap_V1_5_96GB.ipynb](notebooks/minimax-h3-character-swap/H3_Character_Swap_V1_5_96GB.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/minimax-h3-character-swap/H3_Character_Swap_V1_5_96GB.ipynb) |
| Qwen-Image 2.1 | [Qwen_Image_2.1.ipynb](notebooks/qwen-image-2.1/Qwen_Image_2.1.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/qwen-image-2.1/Qwen_Image_2.1.ipynb) |
| Krea 2 | [Krea_2.ipynb](notebooks/krea-2/Krea_2.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/krea-2/Krea_2.ipynb) |
| SeedVR2 | [SeedVR2.ipynb](notebooks/seedvr2/SeedVR2.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/seedvr2/SeedVR2.ipynb) |
| IndexTTS 2.5 | [IndexTTS_2.5.ipynb](notebooks/indextts-2.5/IndexTTS_2.5.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/indextts-2.5/IndexTTS_2.5.ipynb) |
| Qwen3.8-27B | [Qwen3.8_27B.ipynb](notebooks/qwen3.8-27b/Qwen3.8_27B.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/qwen3.8-27b/Qwen3.8_27B.ipynb) |

## H3 V1.5 人物替换

[换人 notebook](notebooks/minimax-h3-character-swap/H3_Character_Swap_V1_5_96GB.ipynb) 面向 96GB RTX 6000，按原来的四步部署使用。运行代码、模型配置、工作流和多人选择控件全部内嵌，只需下载这一本 notebook。

| 工作流 | 功能 |
| --- | --- |
| [01 单人全换](workflows/minimax-h3-character-swap/01_H3_Single_Full_Body.json) | 替换人物、发型与完整服装 |
| [02 只换脸](workflows/minimax-h3-character-swap/02_H3_Face_Only.json) | 用人脸遮罩生成并合成，保留脸外区域 |
| [03 多人替换](workflows/minimax-h3-character-swap/03_H3_Multi_People.json) | 下拉选择 1–5 人，每人一张参考图，逐人生成并保护其他区域 |

默认时长 **0＝整段原视频**，当前工作流最多约 149 秒。三种模式共用模型。先检查遮罩；多人编号按首帧检测顺序排列，不保证从左到右，SAM 描述保持 `person:5`。只换脸与多人效果尚未做 96GB GPU 端到端实测。

已有部署：运行 notebook 第 1 步，再运行末尾的 **“更新现有部署”** 单元格，刷新整个 ComfyUI 页面即可。单独导入 JSON 无法安装多人选择控件。单人 SAM 补检、Cloudflare 打开与服务重启修复均已内嵌，具体说明见 notebook。

## 其他模型的统一运行流程

1. **环境检测**：检测 GPU 型号（A100 / H100 / RTX 6000）、显存容量、BF16 与 CUDA 状态。
2. **安装服务环境**：安装 ComfyUI `v0.43.2`（或 vLLM `0.32.0`）、依赖与 `cloudflared` `2026.10.6`。
3. **下载模型与工作流**：下载全部模型权重并同步工作流。
4. **启动并挂载服务**：启动 `8188` 端口服务，从 Colab 左侧 **🔑 Secrets** 读取 `CF_TUNNEL_TOKEN` 挂载至自有域名。

## 许可

- 代码：[Apache-2.0](LICENSE)
- 模型权重：[MiniMax H3](https://huggingface.co/Comfy-Org/MiniMax-H3) · [Turbo LoRA](https://huggingface.co/lightx2v/Minimax-h3-Turbo) · [Qwen-Image 2.1](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE) · [Krea 2](https://huggingface.co/Comfy-Org/Krea-2) · [SeedVR2](https://huggingface.co/Comfy-Org/SeedVR2) · [IndexTTS-2.5](https://huggingface.co/IndexTeam/IndexTTS-2.5) · [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B)

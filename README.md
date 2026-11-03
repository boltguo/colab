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
| [02 只换脸](workflows/minimax-h3-character-swap/02_H3_Face_Only.json) | 专用 ReActor / inswapper 换脸，保留原片发型、服装和背景 |
| [03 多人替换](workflows/minimax-h3-character-swap/03_H3_Multi_People.json) | 下拉选择 1–5 人，每人一张参考图，逐人生成并保护其他区域 |

默认时长 **0＝整段原视频**，当前预处理最多约 149 秒。01 / 03 共用 H3 基座与 VAEs；02 使用[专用 ReActor 节点](https://github.com/Gourieff/ComfyUI-ReActor/tree/0763f707e3f791323f2e7450d100a25860df546c)，额外约 1.43GiB 模型文件。02 直接逐帧换脸，再通过原片 `face` 遮罩限制回贴范围，默认关闭额外人脸修复，只保存最终 `face-only` 视频。帧数或尺寸变化时停止，避免缺帧输出。先用 3 秒片段检查相似度、表情和遮挡，再处理整段。

02 已在 96GB RTX PRO 6000 上完成 3 秒 / 72 帧短测（736×1344、24fps、保留原声），并检查首、中、末静态帧；整段视频和复杂遮挡的效果仍需验证。

先检查遮罩；多人编号按首帧检测顺序排列，不保证从左到右，SAM 描述保持 `person:5`。多人效果尚未做 96GB GPU 端到端实测。

已有部署：使用本版 notebook，运行第 1 步，再运行末尾的 **“更新现有部署”** 单元格。它安装 02 专用节点和新增权重，锁住已有包版本，复用 H3 基座。首次载入新节点时会重启空闲的 ComfyUI；队列忙时提示完成后重跑，不取消任务。刷新整个 ComfyUI 页面，再从左侧重新打开 02，确认出现 **专用换脸 · ReActor** 和 **帧数检查** 节点；已有画布不会自动更新。工作流备份放在列表之外。单独导入 JSON 不会安装节点、下载权重或安装多人选择控件。

02 使用的 inswapper / buffalo_l 预训练权重限非商业研究，具体使用范围见 [ReActor 上游说明](https://github.com/Gourieff/ComfyUI-ReActor#disclaimer)。

## 其他模型的统一运行流程

1. **环境检测**：检测 GPU 型号（A100 / H100 / RTX 6000）、显存容量、BF16 与 CUDA 状态。
2. **安装服务环境**：安装 ComfyUI `v0.43.2`（或 vLLM `0.32.0`）、依赖与 `cloudflared` `2026.10.6`。
3. **下载模型与工作流**：下载全部模型权重并同步工作流。
4. **启动并挂载服务**：启动 `8188` 端口服务，从 Colab 左侧 **🔑 Secrets** 读取 `CF_TUNNEL_TOKEN` 挂载至自有域名。

## 许可

- 代码：[Apache-2.0](LICENSE)
- 模型权重：[MiniMax H3](https://huggingface.co/Comfy-Org/MiniMax-H3) · [Turbo LoRA](https://huggingface.co/lightx2v/Minimax-h3-Turbo) · [Qwen-Image 2.1](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE) · [Krea 2](https://huggingface.co/Comfy-Org/Krea-2) · [SeedVR2](https://huggingface.co/Comfy-Org/SeedVR2) · [IndexTTS-2.5](https://huggingface.co/IndexTeam/IndexTTS-2.5) · [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B)

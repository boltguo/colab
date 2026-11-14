# AI 模型一键 Colab 工作台与标准 API

支持 **A100**、**H100**、**RTX 6000 (96GB)** 三款显卡，全系模型均已升级为统一的**现代亮色 Web 工作台 + 全参数标准 API**（无需导入或切换任何 `.json` 工作流文件）：
- **MiniMax H3**、**Qwen-Image 2.1** 与 **Qwen3.8-27B（BF16）**：需 **80GB 及以上显存**（A100 80GB / H100 80GB / RTX 6000 96GB）。
- **SeedVR2（FP16）**、**IndexTTS 2.5** 与 **Qwen3.8-27B（FP8）**：**40GB 及以上显存即可**（A100 40GB / 80GB、H100 80GB、RTX 6000 96GB）。

| 模型 | 笔记本 | Colab |
| --- | --- | --- |
| MiniMax H3（现代 Web + 音画视频 API） | [MiniMaxH3.ipynb](notebooks/minimax-h3/MiniMaxH3.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/minimax-h3/MiniMaxH3.ipynb) |
| Qwen-Image 2.1（现代 Web + API） | [Qwen_Image_2.1.ipynb](notebooks/qwen-image-2.1/Qwen_Image_2.1.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/qwen-image-2.1/Qwen_Image_2.1.ipynb) |
| SeedVR2（现代 Web + 视频/图片 4K 超分 API） | [SeedVR2.ipynb](notebooks/seedvr2/SeedVR2.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/seedvr2/SeedVR2.ipynb) |
| IndexTTS 2.5（现代 Web + API） | [IndexTTS_2.5.ipynb](notebooks/indextts-2.5/IndexTTS_2.5.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/indextts-2.5/IndexTTS_2.5.ipynb) |
| Qwen3.8-27B（现代 Web + Claude Code/OpenAI API） | [Qwen3.8_27B.ipynb](notebooks/qwen3.8-27b/Qwen3.8_27B.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/qwen3.8-27b/Qwen3.8_27B.ipynb) |

## MiniMax H3（现代 Web 音画视频工作台 + 全参数 API）

[MiniMax-H3 笔记本](notebooks/minimax-h3/MiniMaxH3.ipynb) 提供统一的**现代亮色前端工作台 + 标准全参数 REST/WebSocket API**：
- **单页全能音画同生**：在一个页面无缝切换文生音画视频（`t2v`）、首帧/首尾帧图生视频（`fl2v`）与多模态参考生视频（`r2v`，自由组合最多 5 张 `<Picture>`、2 段 `<Video>` 及对应原声/独立 `<Audio>`），自动同步合成 32kHz 立体声对白与环境音效。
- **独立画幅时长与 Turbo 加速**：提供独立的分辨率档位（`540p` / `768p` / `1080p`）、宽高比、32px 对齐像素宽高与 `17k+5` 时间帧网格实时换算；支持一键切换官方 **8 步 FL2V Turbo** / **4 步 Ref2V Turbo** 蒸馏加速，以及在线热挂载自定义 `.safetensors` LoRA。

## Qwen-Image 2.1（现代 Web 工作台 + 全参数 API + 动态 LoRA）

[Qwen-Image 2.1 笔记本](notebooks/qwen-image-2.1/Qwen_Image_2.1.ipynb) 提供统一的**现代亮色前端工作台 + 标准全参数 API**：
- **单页全能图像创作与编辑**：在同一工作台内无缝切换 2K/1K 文生图、`<image1>` 单图保主体指令重绘、`<image1>` + `<image2>` 双图主体场景融合及最多 4 图参考组合，配备原图与成片 **A/B 卷帘对比**及一键“设为 `<image1>` 继续精修”。
- **在线动态 LoRA 热加载**：支持一键挂载精选 `Anime Consistency` LoRA，或直接输入任意 Hugging Face 仓库、Civitai / HTTPS `.safetensors` 下载链接与本地文件上传，后台自动完成二进制安全头校验并热挂载（最多 6 层独立强度叠加）。

## SeedVR2（现代 Web 视频/图片 4K 超分工作台 + 全参数 API）

[SeedVR2 笔记本](notebooks/seedvr2/SeedVR2.ipynb) 已将原先拆散的 3 套超分 `.json` 工作流（`7B Sharp` 视频超分、`3B Fast` 视频超分与 `7B Sharp` 图片 4K 超分）融合为单页双模态超分工作台：
- **双规格 1 步对抗超分与精准追色**：在同一界面自由切换 **7B Sharp 旗舰细节版**与 **3B Fast 长视频极速版**，提供按倍数、固定短边档位（`1080P` / `2K` / `4K`）、固定长边与自定义宽高 4 种独立放大策略，内置 **CIELAB / Wavelet / AdaIN** 色彩对齐校正。
- **长视频省显存与同屏 A/B 对比**：内置 **Split Latent** 时间分块（Hann 窗平滑融合消接缝）与 **Tiled VAE** 空间瓦片防爆显存，无损保留原视频帧率与音轨，并支持**视频同步播放 A/B 卷帘同屏对比**与图片原寸放大检视。

## IndexTTS 2.5（现代 Web 工作台 + 标准 API）

[IndexTTS 2.5 笔记本](notebooks/indextts-2.5/IndexTTS_2.5.ipynb) 采用**零 ComfyUI 依赖**的独立现代前端 + FastAPI 架构，运行时直接拉取 GitHub Releases 中的 `app-indextts-2.5.tar.gz` 应用包：
- **单页多合一操作**：在网页中直接完成零样本多语种音色克隆（`zh / en / ja / es / ar`）、8 维情绪滑块控制、双参考音频音色/情绪分离、自然语言情感控制（QwenEmotion）、麦克风在线录音与 `.srt` 时间轴字幕导出。
- **同源 REST / WebSocket API**：对外同时提供 `POST /api/v1/generate`、`POST /api/v1/files`、`GET /api/v1/tasks/{id}`、`WS /api/v1/tasks/{id}/ws` 与 `/docs` Swagger 在线接口文档（网页右上角弹窗可一键复制当前机器的 `curl` / Python 调用代码）。

## Qwen3.8-27B（现代多模态 Web 工作台 + Claude Code / OpenAI API）

[Qwen3.8-27B 笔记本](notebooks/qwen3.8-27b/Qwen3.8_27B.ipynb) 基于原生 `vLLM 0.32.0`（256K 上下文 + MTP 投机采样），80GB 显卡加载 BF16、40GB 显卡自动加载 FP8：
- **多模态对话与深度思考工作台**：支持多轮图文/视频理解、实时可折叠 `<think>` 思考流、全量采样超参与 Function Calling 调试。
- **双协议原生兼容**：同一端口同时提供 Anthropic `/v1/messages`（支持 **Claude Code** 直连）与 OpenAI `/v1/chat/completions` 接口。

## 统一运行流程

1. **环境检测**：检测 GPU 型号（A100 / H100 / RTX 6000）、显存容量、BF16 与 CUDA 状态。
2. **安装服务环境**：安装底层推理引擎（原生推理库 / ComfyUI `v0.43.2` / vLLM `0.32.0`）、拉取对应 Release 应用包与 `cloudflared` `2026.10.6`。
3. **下载模型权重**：高速下载并校验模型权重完整性。
4. **启动并挂载服务**：启动 `8188` 端口服务，默认通过 Cloudflare Quick Tunnel 生成临时公网域名（用完即关）；亦可在第 4 步切换「自有 Tunnel」从 Colab 左侧 **🔑 Secrets** 读取 `CF_TUNNEL_TOKEN` 挂载固定域名。

## 许可

- 代码：[Apache-2.0](LICENSE)
- 模型权重：[MiniMax H3](https://huggingface.co/Comfy-Org/MiniMax-H3) · [Turbo LoRA](https://huggingface.co/lightx2v/Minimax-h3-Turbo) · [Qwen-Image 2.1](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE) · [SeedVR2](https://huggingface.co/Comfy-Org/SeedVR2) · [IndexTTS-2.5](https://huggingface.co/IndexTeam/IndexTTS-2.5) · [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B)

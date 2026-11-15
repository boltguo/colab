# AI 模型一键 Colab 工作台与标准 API

提供统一的**现代亮色 Web 工作台 + 全参数标准 API**（无需导入或切换任何 `.json` 工作流文件）。笔记本按以下显卡与显存门槛选择运行配置：

- **MiniMax H3**、**Qwen-Image 2.1** 与 **Qwen3.8-27B（BF16）**：需 **80GB 及以上显存**（A100 80GB / H100 80GB / RTX 6000 96GB）。
- **SeedVR2（FP16）**、**IndexTTS 2.5** 与 **Qwen3.8-27B（FP8）**：配置门槛为 **40GB 及以上显存**（A100 40GB / 80GB、H100 80GB、RTX 6000 96GB）。实际可运行的上下文长度、分辨率与视频时长需在目标 GPU 上验证。

| 模型 | 笔记本 | Colab |
| --- | --- | --- |
| MiniMax H3（现代 Web + 音画视频 API） | [MiniMaxH3.ipynb](notebooks/minimax-h3/MiniMaxH3.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/minimax-h3/MiniMaxH3.ipynb) |
| Qwen-Image 2.1（现代 Web + API） | [Qwen_Image_2.1.ipynb](notebooks/qwen-image-2.1/Qwen_Image_2.1.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/qwen-image-2.1/Qwen_Image_2.1.ipynb) |
| SeedVR2（现代 Web + 视频/图片 4K 超分 API） | [SeedVR2.ipynb](notebooks/seedvr2/SeedVR2.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/seedvr2/SeedVR2.ipynb) |
| IndexTTS 2.5（现代 Web + API） | [IndexTTS_2.5.ipynb](notebooks/indextts-2.5/IndexTTS_2.5.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/indextts-2.5/IndexTTS_2.5.ipynb) |
| Qwen3.8-27B（现代 Web + Claude Code/OpenAI API） | [Qwen3.8_27B.ipynb](notebooks/qwen3.8-27b/Qwen3.8_27B.ipynb) | [![在 Colab 打开](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/qwen3.8-27b/Qwen3.8_27B.ipynb) |

## MiniMax H3（现代 Web 音画视频工作台 + 全参数 API）

[MiniMax-H3 笔记本](notebooks/minimax-h3/MiniMaxH3.ipynb) 提供统一的**现代亮色前端工作台 + 标准全参数 REST/WebSocket API**：
- **单页全能音画同生**：在一个页面无缝切换文生音画视频（`t2v`）、首帧/首尾帧图生视频（`fl2v`）与多模态参考生视频（`r2v`，最多 9 张 `<Picture>`、3 段 `<Video>` 与 3 段独立 `<Audio>`，混合输入合计最多 12 个文件，视频原声不另计），自动同步合成 32kHz 立体声对白与环境音效。
- **独立画幅时长与 Turbo 加速**：当前接入 **H3-Base 原生 768p**，另提供 `540p` 低清试跑、独立宽高比、32px 对齐的实验性自定义画布与 `17k+5` 时间帧网格实时换算；当前未接入官方 `H3-Regenerate-2K`，自定义尺寸不代表已支持原生 1080p / 2K 或超分。支持一键切换官方 **8 步 FL2V Turbo** / **4 步 Ref2V Turbo** 蒸馏加速，以及在线热挂载自定义 `.safetensors` LoRA。模型规格见 [官方说明](https://github.com/MiniMax-AI/MiniMax-H3#system-overview)。
- 有声输出使用模型原生 **24 FPS**；静音输出可调整播放帧率，时长随之变化。参考视频会先统一为 24 FPS，保持参考动作与音轨的时间对应。

## Qwen-Image 2.1（现代 Web 工作台 + 全参数 API + 动态 LoRA）

[Qwen-Image 2.1 笔记本](notebooks/qwen-image-2.1/Qwen_Image_2.1.ipynb) 提供统一的**现代亮色前端工作台 + 标准全参数 API**：
- **单页全能图像创作与编辑**：在同一工作台内切换 2K/1K 文生图、单图编辑、双图融合及最多 10 图参考组合，保留透明参考图的 Alpha 通道，常用 2K 画幅对齐官方推荐尺寸，配备原图与成片 **A/B 卷帘对比**及一键继续精修。
- **在线动态 LoRA 热加载**：支持一键挂载精选 `Anime Consistency` LoRA，或直接输入任意 Hugging Face 仓库、Civitai / HTTPS `.safetensors` 下载链接与本地文件上传，后台自动完成二进制安全头校验并热挂载（最多 6 层独立强度叠加）。

## SeedVR2（现代 Web 视频/图片 4K 超分工作台 + 全参数 API）

[SeedVR2 笔记本](notebooks/seedvr2/SeedVR2.ipynb) 已将原先拆散的 3 套超分 `.json` 工作流（`7B Sharp` 视频超分、`3B Fast` 视频超分与 `7B Sharp` 图片 4K 超分）融合为单页双模态超分工作台：
- **双规格 1 步对抗超分与精准追色**：在同一界面自由切换 **7B Sharp 旗舰细节版**与 **3B Fast 长视频极速版**，提供按倍数、固定短边档位（`1080P` / `2K` / `4K`）、固定长边与自定义宽高 4 种独立放大策略，内置 **CIELAB / Wavelet / AdaIN** 色彩对齐校正。
- **长视频省显存与同屏 A/B 对比**：内置 **Split Latent** 时间分块（支持单帧及 `4n+1` 帧分块、Hann 窗融合）与 **Tiled VAE** 空间瓦片控制。保持原速时可保留原声内容，音轨随成片重新编码，不保证位流无损。支持**视频同步播放 A/B 卷帘同屏对比**与图片原寸放大检视。4K 需按实际源尺寸或目标宽高设置，4 倍放大不等于固定 4K。
- 播放帧率填 `0` 保持原速；指定其他帧率会改变播放速度，需关闭原声音轨。该控制不进行补帧；A/B 对比会按裁剪起点及播放速度对齐。

## IndexTTS 2.5（现代 Web 工作台 + 标准 API）

[IndexTTS 2.5 笔记本](notebooks/indextts-2.5/IndexTTS_2.5.ipynb) 采用**零 ComfyUI 依赖**的独立现代前端 + FastAPI 架构，运行时直接拉取 GitHub Releases 中的 `app-indextts-2.5.tar.gz` 应用包：
- **单页多合一操作**：在网页中直接完成零样本多语种音色克隆（`zh / en / ja / es / ar`）、8 维情绪滑块控制、双参考音频音色/情绪分离、自然语言情感控制（QwenEmotion）、麦克风在线录音与 `.srt` 时间轴字幕导出。
- **同源 REST / WebSocket API**：对外同时提供 `POST /api/v1/generate`、`POST /api/v1/files`、`GET /api/v1/tasks/{id}`、`WS /api/v1/tasks/{id}/ws` 与 `/docs` Swagger 在线接口文档（网页右上角弹窗可一键复制当前机器的 `curl` / Python 调用代码）。
- 字幕时间轴按文本长度估算，导出后可按实际音频校准。

## Qwen3.8-27B（现代多模态 Web 工作台 + Claude Code / OpenAI API）

[Qwen3.8-27B 笔记本](notebooks/qwen3.8-27b/Qwen3.8_27B.ipynb) 基于原生 `vLLM 0.32.0`，启用 MTP 投机采样；80GB 显卡选择 BF16，40GB 显卡选择 FP8。256K 是笔记本的上下文配置上限，本轮未验证 40GB 显卡可用的最大长度。

- **多模态对话与深度思考工作台**：支持多轮图文/视频理解、可折叠思考流、`low / medium / xhigh` 思考强度、可选保留历史思考、常用采样超参与 Function Calling 调试；默认思考温度按官方设置为 `1.0`。更多 vLLM 参数可通过 `/v1/chat/completions` 透传，工作台不自动执行工具调用。
- **双协议原生兼容**：同一端口同时提供 Anthropic `/v1/messages`（支持 **Claude Code** 直连）与 OpenAI `/v1/chat/completions` 接口。

## 统一运行流程

1. **环境检测**：检测 GPU 型号（A100 / H100 / RTX 6000）、显存容量、BF16 与 CUDA 状态。
2. **安装服务环境**：安装底层推理引擎（原生推理库 / ComfyUI `v0.43.2` / vLLM `0.32.0`）、拉取对应 Release 应用包与 `cloudflared` `2026.10.6`。
3. **下载模型权重**：高速下载并校验模型权重完整性。
4. **启动并挂载服务**：启动 `8188` 端口服务，默认通过 Cloudflare Quick Tunnel 生成临时公网域名（用完即关）；亦可在第 4 步切换「自有 Tunnel」从 Colab 左侧 **🔑 Secrets** 读取 `CF_TUNNEL_TOKEN` 挂载固定域名。

## 开发与检查

使用 Python 3.12、Node.js 22.18+ 和 pnpm 11。媒体回归用例需要系统安装 `ffmpeg`、`ffprobe`。

```bash
python3 -m pip install -r tests/requirements.txt
python3 -m unittest discover -s tests -p 'test_*.py' -v
pnpm -C frontend install --frozen-lockfile
pnpm -C frontend test
pnpm -C frontend typecheck
pnpm -C frontend build:all
python3 tools/build_notebooks.py
```

构建后可运行单个工作台的预览服务：

```bash
python3 backend/run_server.py --feature indextts-2.5 --mock
```

Mock 模式用于检查界面和 API 流程；真实模型效果与显存需求需在目标 GPU 上验证。

## 更新 Colab 应用

笔记本第 2 步使用由 `tools/release_manifest.json` 写入的固定 Release 地址和哈希。源码改动合并后，在 GitHub Actions 手动运行 **Build & Publish Feature App Releases**，填写未使用的新版本号；工作流会构建五个应用包并同步笔记本哈希。已存在的版本禁止覆盖，以保证旧笔记本仍能通过校验。

发布后请重新打开仓库中的最新笔记本。若要继续使用已有 Colab 运行时，先将第 2、4 步更新为最新内容，再运行这两步；仅重跑旧单元格仍会安装旧版本。第 4 步会根据应用包、API Key 和服务配置的变化重启对应服务。若新版本同时变更模型或引擎依赖，请按最新笔记本完整运行四步。

本轮逐项审查记录见 [工作台审查与改进](docs/studio-review-2026-11-15.md)。
官方能力、参数映射、尚未集成的扩展能力与验证范围见 [四模型官方核对](docs/model-capability-audit-2026-11-15.md)。

## 许可

- 代码：[Apache-2.0](LICENSE)
- 模型权重：[MiniMax H3](https://huggingface.co/Comfy-Org/MiniMax-H3) · [Turbo LoRA](https://huggingface.co/lightx2v/Minimax-h3-Turbo) · [Qwen-Image 2.1](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE) · [SeedVR2](https://huggingface.co/Comfy-Org/SeedVR2) · [IndexTTS-2.5](https://huggingface.co/IndexTeam/IndexTTS-2.5) · [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B)

# Colab

在 Colab 运行图像、视频、语音和对话模型。选择对应笔记本，启动后打开页面即可使用。

| 模型 | 建议显存 | 简介 | 一键打开 |
| --- | --- | --- | --- |
| [Qwen-Image 2.1](notebooks/qwen-image-2.1/Qwen_Image_2.1.ipynb) | 80GB+ | 文生图、图像编辑、多图参考 | [![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/qwen-image-2.1/Qwen_Image_2.1.ipynb) |
| [MiniMax-H3](notebooks/minimax-h3/MiniMaxH3.ipynb) | 80GB+ | 有声视频、首尾帧、多模态参考 | [![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/minimax-h3/MiniMaxH3.ipynb) |
| [H3 Character Swap](notebooks/h3-character-swap/H3_Character_Swap.ipynb) | 80GB+（推荐）/ 40GB+（480p） | 单人 / 多人视频人物替换，保留动作与原声 | [![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/h3-character-swap/H3_Character_Swap.ipynb) |
| [SeedVR2](notebooks/seedvr2/SeedVR2.ipynb) | 40GB+ | 视频和图片放大、细节修复 | [![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/seedvr2/SeedVR2.ipynb) |
| [IndexTTS 2.5](notebooks/indextts-2.5/IndexTTS_2.5.ipynb) | 40GB+ | 音色克隆、语速和情绪控制 | [![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/indextts-2.5/IndexTTS_2.5.ipynb) |
| [Qwen3.8-27B](notebooks/qwen3.8-27b/Qwen3.8_27B.ipynb) | 40GB+（FP8）/ 80GB+（BF16） | 对话、深度思考、图片与视频理解 | [![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/boltguo/colab/blob/main/notebooks/qwen3.8-27b/Qwen3.8_27B.ipynb) |

以上按本仓库的笔记本配置选择 GPU，实际显存用量随分辨率、视频长度和上下文长度变化。每个笔记本独立运行一个模型。

## Web 页面

上传素材、填写文本或提示词，再调整尺寸、步数、种子等常用设置。底部选择输出格式和数量，点击生成；结果可以预览、下载，也可以从本次历史中再次使用。

专业采样、缓存、推理精度和编码细节使用默认值。页面右上角可查看实时机器资源与切换中/英文界面。

![Qwen-Image 2.1 Web 页面](docs/images/qwen-image-studio.png)

## 使用说明

1. 从上方表格选择模型，并在 Colab 中连接符合要求的 GPU。
2. 在浏览器打开笔记本后，依次运行第 1–4 步即可。
3. 第 4 步通过 Google Colab 官方内置端口代理（`proxyPort`）启动 Web 页面，仅绑定当前登录的 Google 账号访问，无需配置外部隧道或额外密码，也不开放外部 API；实例停止后临时链接即失效。
4. 建议先用默认设置（或 40GB 显存下先用 `480p` / `5s`）测试一次，再按需要调整尺寸、时长、步数或种子。

## 模型与功能

### Qwen-Image 2.1

支持文生图和图像编辑，最多使用 10 张参考图。可以选择 1K / 2K、画幅比例或自定义尺寸，一次生成 1～4 张；编辑结果支持与原图对比、继续精修。

### MiniMax-H3

支持文生视频、首尾帧和图片/视频/音频参考，最多 9 张参考图，混合素材合计最多 12 份。当前提供 540p / 768p；极速模式会自动选择推荐步数。

### H3 Character Swap

基于 `MiniMax-H3 Ref2VA + FL2V Turbo 8-step + Character Swap V1.5 + SAM 3.1`，支持单人替换与多人同框分别替换（1–4 位角色），通过 `SAM 3.1` 自动跟踪人物并锁定原视频背景，完整替换人物脸部与全身服饰同时保留动作、光影和原声，支持可选关键帧锚点引导与 A/B 卷帘视频对比。

### SeedVR2

上传视频或图片，选择按倍数或目标尺寸放大。7B Sharp 偏重清晰度，3B Fast 偏重速度；视频可保留原声，结果支持放大前后对比。

### IndexTTS 2.5

使用内置 Sage 音色，或上传、录制自己的参考人声。支持中文、英语、日语、西班牙语和阿拉伯语，可调整语速、描述语气或使用情绪参考音频。

### Qwen3.8-27B

支持文字、图片和视频多轮对话，在 Web 工作台内置实时可折叠深度思考流、回复长度与采样随机度设置。

### 挂载 LoRA

在 Qwen-Image 或 MiniMax 中展开「风格模型（LoRA，可选）」：选择已有模型、粘贴模型链接，或上传本地 `.safetensors` 文件。启用后调整强度，再正常生成即可；多个模型可以叠加使用。

<details>
<summary>本地开发与更新</summary>

本地开发使用 Python 3.12、Node.js 22.18+、pnpm 11；媒体处理需要 FFmpeg。

```bash
pnpm -C frontend install --frozen-lockfile
pnpm -C frontend build:all
python3 -m pip install -r backend/requirements.txt
python3 backend/run_server.py --feature indextts-2.5 --mock
```

`--mock` 用于检查界面和调用流程。真实推理需要对应权重和 GPU。

Colab 从 GitHub Releases 安装预构建应用。源码更新后，运行 GitHub Actions 的 **Build & Publish Feature App Releases** 发布新版本并同步笔记本，再使用最新笔记本运行安装与启动步骤。

</details>

## 许可

代码采用 [Apache-2.0](LICENSE)。模型权重请遵循各项目许可证：[Qwen-Image](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE)、[MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3)、[H3 Character Swap LoRA](https://huggingface.co/akatz-ai/MiniMax-H3-Character-Swap-LoRA)、[SeedVR2](https://huggingface.co/Comfy-Org/SeedVR2)、[IndexTTS](https://huggingface.co/IndexTeam/IndexTTS-2.5)、[Qwen3.8](https://huggingface.co/Qwen/Qwen3.8-27B)。

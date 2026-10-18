# IndexTTS 2.5 工作流

- **配套笔记本**：[IndexTTS_2.5.ipynb](../../notebooks/indextts-2.5/IndexTTS_2.5.ipynb)
- **支持显卡**：A100 (40GB / 80GB)、H100 (80GB)、RTX 6000 (96GB)
- **模型仓库**：[`IndexTeam/IndexTTS-2.5`](https://huggingface.co/IndexTeam/IndexTTS-2.5)
- **支持语种**：中文（`zh`）、英文（`en`）、日语（`ja`）、西班牙语（`es`）、阿拉伯语（`ar`），支持跨语种音色克隆
- **输出目录**：`/content/ComfyUI/output/indextts-2.5/`

## 工作流列表

| 文件 | 模式 | 输入要求 | 情感控制方式 | 输出前缀 |
| --- | --- | --- | --- | --- |
| [01_IndexTTS_2_5_Clone.json](01_IndexTTS_2_5_Clone.json) | 基础声音克隆 | 1 段音色参考音频 + 文本 | 默认继承参考音频情绪，也可填 `emo_text` 用文字描述情绪 | `indextts-2.5/clone/IndexTTS25` |
| [02_IndexTTS_2_5_Emotion_Vector.json](02_IndexTTS_2_5_Emotion_Vector.json) | 情绪滑块控制克隆 | 1 段音色参考音频 + 8 维情绪滑块 + 文本 | 通过 `Emo Settings` 节点调节 8 种情绪强度（`0~1`） | `indextts-2.5/emo_vector/IndexTTS25` |
| [03_IndexTTS_2_5_Emotion_Ref.json](03_IndexTTS_2_5_Emotion_Ref.json) | 音色与情绪分离克隆 | 音色参考音频 + 情绪参考音频 + 文本 | 第 1 段音频提供音色，第 2 段音频提供情绪语气 | `indextts-2.5/emo_ref/IndexTTS25` |

## 使用方法

1. 按顺序运行 [IndexTTS_2.5.ipynb](../../notebooks/indextts-2.5/IndexTTS_2.5.ipynb) 的 4 个步骤，通过 Cloudflare Tunnel 绑定的域名打开 ComfyUI。
2. 在左侧工作流列表中打开 `01`～`03` 任一工作流。
3. 在「上传音色参考音频」节点使用预置的 `ref_audio.mp3` 或上传 `3~15` 秒清晰人声。
4. 在中间节点输入目标文本（支持中文多音字拼音标注，如 `他在银<行|XING2>里<行|HANG2>走`），调节 `duration_factor`（语速 `0.5~2.0`），点击运行即可在右侧节点试听并保存 MP3。


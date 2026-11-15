# 四模型官方能力与参数核对

核对日期：2026-11-15。范围为当前接入的四个模型及锁定引擎；按本轮要求，只修正明确错误，保留现有布局、主要参数范围和推理架构。

## 结论与本轮处理

| 模型 | 核对结果 | 本轮处理 |
| --- | --- | --- |
| Qwen-Image 2.1 | 官方最多 10 张参考图，界面只开放 4 张、API 只允许 8 张；透明参考图的 Alpha 未接到编码器；尺寸读取遗漏 EXIF 旋转，原图模式可能静默截断尺寸 | 对齐 10 图上限；将 LoadImage 的 RGB 与透明遮罩重新组成 RGBA；按 EXIF 读取真实尺寸，损坏图片明确报错，超出原图模式工作台范围时提示改选分辨率 |
| Qwen3.8-27B | 使用了旧模型的 high 档位和思考温度 0.6；锁定权重模板接受 xhigh / medium / low，官方思考温度为 1.0；历史思考被丢弃，缺少 preserve_thinking 开关 | 修正档位和推荐默认值；保留模型返回的历史 reasoning_content，提供 preserve_thinking 开关并同步 API 导出；非思考推荐组合为温度 0.7、Top-P 0.8、Presence Penalty 1.5 |
| SeedVR2 | 1 步采样、四种色彩校正、时间分块连线正确；单帧分块被界面和 API 排除；原声重新编码却写成无损；4 倍放大被描述为固定 4K | 补齐 1 帧分块；更正文案，保留现有分块/VAE 参数范围和默认值 |
| IndexTTS 2.5 | 五语种、8 维情绪顺序/偏置、语速、分句、GPT2 采样、25 步 CFM / 0.7 CFG 的映射吻合 | 保留现有实现；笔记本补充字幕为估算时间轴的说明 |

## 已核对的主要参数

- **Qwen-Image**：统一文生图/编辑、参考图编号、原生 2K、1K 与原图画布、批量数、40 步/CFG=1、采样器/调度器、LoRA 叠加、KV 缓存设备与 int8/int4 精度、PNG/WebP/JPEG 导出。现有画幅按约 4MP 与 32px 对齐计算，和官方推荐表略有差别仍属有效尺寸；本轮保留，不改动生成尺寸习惯。透明生成通过官方推荐的提示词控制，PNG/WebP 可保留 Alpha，JPEG 不支持透明。
- **Qwen3.8**：原生 262144 上下文、MTP 启动配置、思考/非思考、思考档位、历史思考、温度/Top-P/Top-K/Min-P、三种惩罚、种子、停止词、JSON 对象模式、工具调试、图像/视频附件与 OpenAI/Anthropic 网关。256K 是上下文上限，包含输入和输出，不代表 40GB 显卡已验证能跑满。
- **SeedVR2**：7B Sharp/3B 权重选择、按倍数/短边/长边/自定义尺寸、CIELAB/Wavelet/AdaIN/none、4n+1 时间网格、分块与重叠、空间/时间 VAE 瓦片、裁剪、原速/变速、原声、Alpha 与编码。单帧分块由固定 ComfyUI 节点支持；多步采样保留为实验设置，不保证更高质量。
- **IndexTTS**：zh/en/ja/es/ar、8 维情绪与双参考、QwenEmotion 文本控制、duration_factor、参考截取、文本正则化、分句阈值/停顿、do_sample/top_p/top_k/temperature/num_beams/重复与长度惩罚/max_mel_tokens、CFM 步数/CFG、BF16/CUDA 算子/torch.compile、响度/静音/淡出和输出格式。默认 120 文本 Token、GPT2 温度/Top-P=0.8、Top-K=30、num_beams=3，与固定推理源码吻合。

## 发现但本轮不扩展的能力

- Qwen-Image 官方独立 Turbo 权重、PE 提示词扩写模型与专用遮罩绘制界面尚未集成；原始模型与 Turbo 的采样日程不同，不能把普通模型改成 8 步就称为官方 Turbo。已有图像输入仍可上传用户自行标注的参考图。
- Qwen3.8 的 1M 上下文需要额外 YaRN/运行时配置；当前维持 256K。工作台只提供常用采样控件，更多 vLLM 字段走原生 `/v1/chat/completions` 透传；界面只预览工具调用，不执行函数。
- IndexTTS 原生构造器还支持 `use_deepspeed` / `use_accel`，当前固定关闭；本轮不增加加速后端或依赖安装。原生分块音频流接口也未纳入当前异步任务/完整音频文件输出流程。
- 一些宽高、批量、文本长度和瓦片范围是工作台限制，并非官方模型硬上限。本轮未为追求参数数量而全面放开范围。

## 核对来源与版本

- [Qwen-Image 2.1 官方说明](https://github.com/QwenLM/Qwen-Image-2.1)：10 图、原生 RGBA、2K、40 步、独立 Turbo 与 PE。
- [固定 ComfyUI Qwen 节点](https://github.com/Comfy-Org/ComfyUI/blob/423cbd20511becb1f16122ab518e92e58bfa03d9/comfy_extras/nodes_qwen.py)：编码器最多提供 16 个接口槽，但本应用按官方模型规格限制为 10 张；参考 Alpha、参考分辨率和 KV 缓存映射。
- [Qwen3.8 固定权重模型卡](https://huggingface.co/Qwen/Qwen3.8-27B/blob/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0/README.md)、[固定聊天模板](https://huggingface.co/Qwen/Qwen3.8-27B/blob/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0/chat_template.jinja)：xhigh、默认温度、preserve_thinking 和上下文范围；[vLLM 0.32.0](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/sampling_params.py) 对照采样语义。
- [SeedVR 官方仓库](https://github.com/ByteDance-Seed/SeedVR)、[固定 ComfyUI SeedVR2 节点](https://github.com/Comfy-Org/ComfyUI/blob/423cbd20511becb1f16122ab518e92e58bfa03d9/comfy_extras/nodes_seedvr.py)、[视频节点](https://github.com/Comfy-Org/ComfyUI/blob/423cbd20511becb1f16122ab518e92e58bfa03d9/comfy_extras/nodes_video.py)：1 步、色彩算法、单帧/4n+1 分块及视频组件重新封装。
- [IndexTTS 固定推理源码](https://github.com/index-tts/index-tts/blob/d9e41aac89fd00b3d71497fddb287b7f24613712/indextts/infer_v2_5.py)、[固定模型配置](https://huggingface.co/IndexTeam/IndexTTS-2.5/blob/c39ce5ba981572cb187443877ff559dfb246ce63/config.yaml)：主参数默认值与原生构造器选项。

## 验证边界

验证通过：五个前端 TypeScript/生产构建、15 项 Node 测试、76 项 Python 回归测试（含 Mock API 上传、异步任务、流式对话及下载流程），五份生成笔记本的代码语法检查。本轮未重新做五个页面的完整视觉验收，未运行 Colab、未加载 GPU 权重。模型质量、加速收益和最大可用上下文仍需目标 GPU 验证。Release 哈希保持现有真实值，本地修改不会自动进入现有 Colab 应用包。

"""生成 notebooks/ 下全部笔记本的第 1–4 步：python3 tools/build_notebooks.py"""
import ast, json, os, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
tpl = {p.stem: p.read_text(encoding="utf-8") for p in (ROOT / "tools/templates").glob("*.py")}
HELPERS = tpl["helpers"]
RELEASE_MANIFEST = json.loads((ROOT / "tools/release_manifest.json").read_text(encoding="utf-8"))

REQ80 = "80GB-class VRAM (A100 80GB / H100 80GB / RTX 6000 96GB)"
REQ40 = "40GB+ VRAM (A100 40GB/80GB, H100 80GB, RTX 6000 96GB)"

MD1 = """### 1. 环境检测
- **功能**：检测 GPU 型号、显存容量、BF16 支持、系统内存、磁盘空间及 PyTorch / CUDA 版本。
- **要求**：{req}
- **使用**：直接运行，输出 `[OK]` 后继续。"""
MD2_COMFY_APP = """### 2. 安装内部推理引擎与 Web 工作台
- **功能**：安装内部无头 GPU 推理算子引擎（ComfyUI `v0.43.2`）及 Web 工作台运行依赖，并拉取校验 GitHub Release 发布的 `{archive}`（`{tag}`，内含编译好的现代前端 `dist` 与本地 Web 后端）。
- **使用**：直接运行，输出 `[OK]` 后继续。"""
MD2_INDEXTTS = """### 2. 安装 IndexTTS 2.5 引擎与 Web 工作台
- **功能**：安装官方 `index-tts` 推理引擎及 Web 工作台依赖，并拉取校验 GitHub Release 发布的 `{archive}`（`{tag}`，内含编译好的现代前端 `dist` 与本地 Web 后端）。
- **使用**：直接运行，输出 `[OK]` 后继续。"""
MD2_VLLM = """### 2. 安装 vLLM 推理引擎与 Web 工作台
- **功能**：安装 vLLM `0.32.0`、`hf_xet` 与 Web 工作台依赖，并拉取校验 GitHub Release 发布的 `{archive}`（`{tag}`，内含多模态对话前端工作台与本地后端）。
- **使用**：直接运行，输出 `[OK]` 后继续。"""
MD3_COMFY_APP = """### 3. 下载并校验基础模型权重
- **功能**：高速下载并精确校验{models}至 `{model_dir}`（自定义风格或角色 `.safetensors` LoRA 无需在此预先全量下载，启动后可在 Web 工作台中按需在线热挂载）。
- **使用**：直接运行，输出 `[OK]` 后继续。"""
MD3_SEEDVR2 = """### 3. 下载并校验 SeedVR2 双规格权重与 VAE
- **功能**：高速下载并精确校验{models}至 `{model_dir}`（启动后可在 Web 工作台中自由切换 `7B Sharp` 旗舰锐化版与 `3B Fast` 长视频极速版）。
- **使用**：直接运行，输出 `[OK]` 后继续。"""
MD3_INDEXTTS = """### 3. 下载 IndexTTS 2.5 模型权重
- **功能**：下载{models}至 `{model_dir}`，并预缓存辅助特征提取与声码器模型。
- **使用**：直接运行，输出 `[OK]` 后继续。"""
MD3_VLLM = """### 3. 下载 Qwen3.8-27B 模型
- **功能**：按显存下载模型至 `/content/models`：80GB 及以上为 `Qwen/Qwen3.8-27B` BF16（约 55 GB），40GB 为 `Qwen/Qwen3.8-27B-FP8`（约 28 GB）。
- **使用**：直接运行，输出 `[OK]` 后继续。"""
MD4_APP = """### 4. 启动 Web 工作台（Colab 原生代理）
- **功能**：在本地回环地址（`127.0.0.1:8188`）启动 Web Studio，并通过 **Google Colab 原生端口代理** 生成当前浏览器的专属安全访问链接。
- **访问说明**：无需设置密码或配置第三方隧道，直接由当前登录的 Google 账号鉴权访问；不开放外部 API，实例停止后临时链接失效。
- **使用**：请在浏览器打开本 Colab 笔记本并直接运行下方单元格，完成后点击输出的链接打开工作台。"""
MD4_VLLM = """### 4. 启动多模态对话 Web 工作台（Colab 原生代理）
- **功能**：在本地回环端口启动内部 `vllm serve`（`127.0.0.1:8189`，`262144` 上下文，MTP 投机采样）与 Web Studio 后端（`127.0.0.1:8188`），并通过 **Google Colab 原生端口代理** 打开网页对话工作台。
- **访问说明**：仅限当前登录的 Google 账号通过浏览器访问，无需密码或第三方隧道，不开放外部 `/v1/*` API 网关；实例停止后临时链接失效。
- **使用**：请在浏览器打开本 Colab 笔记本并直接运行下方单元格，完成后点击输出的链接打开网页工作台。"""

METADATA = lambda name: {
    "accelerator": "GPU",
    "colab": {"gpuType": "A100", "name": name, "provenance": []},
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
}

def fill(text, **values):
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    assert "{{" not in text, re.findall(r"\{\{\w+\}\}", text)
    return text

def set_source(cell, text, code):
    text = text.rstrip("\n")
    if code:
        ast.parse(text)
    cell["source"] = text.splitlines(keepends=True)

H3 = ("H3", "Comfy-Org/MiniMax-H3", "e5eb578a89295337b8ff433a035929ce0279e0b6", "")
TURBO = ("TURBO", "lightx2v/Minimax-h3-Turbo", "30f485ed874aa44c8183348ad361c5eabad318da", "loras")
QWEN = ("QWEN", "Comfy-Org/Qwen-Image-2.1", "cb504a4090723e43f17ad01cec0359490e2de613", "")
SEEDVR2 = ("SEEDVR2", "Comfy-Org/SeedVR2", "df48879708206a403d2a61acd55578c2e80fd233", "")
INDEXTTS = ("INDEXTTS", "IndexTeam/IndexTTS-2.5", "c39ce5ba981572cb187443877ff559dfb246ce63", "")
H3_SWAP_BASE = ("H3_SWAP_BASE", "Comfy-Org/MiniMax-H3", "4b53a35191437de05370da548e59aeabe2a5a09a", "")
H3_SWAP_LORA = ("H3_SWAP_LORA", "akatz-ai/MiniMax-H3-Character-Swap-LoRA", "96ea3407b230b6f7df71c58c70e31df96bd7e533", "loras")
SAM3 = ("SAM3", "Comfy-Org/sam3.1", "7bb8374780a725b4353ed31f3a9395c9742b5621", "")

STEP3 = {
    "minimax-h3": dict(models=" MiniMax H3 FL2VA / Ref2VA 音画同生主模型、Qwen3-VL-32B 编码器、双模态 VAE 与官方 8/4 步 Turbo LoRA", files=[
        (H3, "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors", 20970379616),
        (H3, "diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors", 20970379616),
        (H3, "text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors", 27141342152),
        (H3, "vae/minimax_h3_video_vae_int8_convrot.safetensors", 2811065184),
        (H3, "vae/minimax_h3_audio_vae_fp32.safetensors", 605254808),
        (H3, "loras/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors", 1956193000),
        (TURBO, "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors", 1956193000),
    ]),
    "qwen-image-2.1": dict(models=" Qwen-Image 2.1 BF16 核心权重（主模型 + Qwen3-VL-8B + VAE）", files=[
        (QWEN, "diffusion_models/qwen_image_2.1_bf16.safetensors", 14230280616),
        (QWEN, "text_encoders/qwen3vl_8b_bf16.safetensors", 17534334616),
        (QWEN, "vae/qwen_image_2.1_vae_bf16.safetensors", 675509688),
    ]),
    "seedvr2": dict(models=" SeedVR2 FP16 `7B Sharp`、`3B Fast` 与 `EMA VAE`", files=[
        (SEEDVR2, "diffusion_models/seedvr2_7b_sharp_fp16.safetensors", 16480583960),
        (SEEDVR2, "diffusion_models/seedvr2_3b_fp16.safetensors", 6784268336),
        (SEEDVR2, "vae/seedvr2_ema_vae_fp16.safetensors", 501324814),
    ]),
    "indextts-2.5": dict(models=" IndexTTS-2.5 权重（含 QwenEmotion）与辅助编码器 / 声码器", model_dir="/content/models/IndexTTS-2.5", files=[
        (INDEXTTS, f, s) for f, s in [
            ("config.yaml", 2860), ("gpt.pth", 3259599833), ("s2mel.pth", 414908601), ("codec.pth", 607290935),
            ("wav2vec2bert_stats.pt", 9343), ("feat1.pt", 57170), ("feat2.pt", 374866),
            ("multilingual_zh_ja_yue_char_del.tiktoken", 907395),
            ("qwen0.6bemo4-merge/Modelfile", 360), ("qwen0.6bemo4-merge/added_tokens.json", 707),
            ("qwen0.6bemo4-merge/chat_template.jinja", 550), ("qwen0.6bemo4-merge/config.json", 727),
            ("qwen0.6bemo4-merge/generation_config.json", 117), ("qwen0.6bemo4-merge/merges.txt", 1671853),
            ("qwen0.6bemo4-merge/model.safetensors", 1192135096), ("qwen0.6bemo4-merge/special_tokens_map.json", 616),
            ("qwen0.6bemo4-merge/tokenizer.json", 11422654), ("qwen0.6bemo4-merge/tokenizer_config.json", 5433),
            ("qwen0.6bemo4-merge/vocab.json", 2776833),
        ]]),
    "h3-character-swap": dict(
        models=" `MiniMax-H3 Ref2VA INT8`, `FL2V Turbo 8-step`, `Character Swap LoRA V1.5`, `SAM 3.1 Multiplex`, `Qwen3-VL-32B-INT8`, `H3 Video VAE` & `H3 Audio VAE`（基于 Ref2VA + SAM 3.1 遮罩的人物与多人物替换）",
        files=[
            (H3_SWAP_BASE, "diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors", 20970379616),
            (H3_SWAP_BASE, "loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors", 1956193000),
            (H3_SWAP_LORA, "h3_character_swap_v1.5.safetensors", 155110792),
            (SAM3, "checkpoints/sam3.1_multiplex_fp16.safetensors", 1745546848),
            (H3_SWAP_BASE, "text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors", 27141342152),
            (H3_SWAP_BASE, "vae/minimax_h3_video_vae_fp16.safetensors", 5207808496),
            (H3_SWAP_BASE, "vae/minimax_h3_audio_vae_fp32.safetensors", 605254808),
        ],
    ),
}

def step3_comfy_app(key, md_template=MD3_COMFY_APP, english_units=False):
    c = STEP3[key]
    sources = []
    for source, *_ in c["files"]:
        if source not in sources:
            sources.append(source)
    total = sum(size for _, _, size in c["files"])
    text = fill(tpl["step3_comfy_app"],
        MODEL_SOURCES="".join(f'{name} = ({json.dumps(repo)}, {json.dumps(rev)}, {json.dumps(folder)})\n' for name, repo, rev, folder in sources),
        MODEL_FILES="".join(f'    (*{s[0]}, {json.dumps(f)}, {size}),\n' for s, f, size in c["files"]),
        POST_DOWNLOAD=c.get("post", ""))
    size_note = f" ({total / 1024**3:.1f} GiB)" if english_units else f"（约 {total / 1024**3:.1f} GB）"
    md = md_template.format(models=f"{c['models']}{size_note}", model_dir=c.get("model_dir", "/content/ComfyUI/models"))
    return text, md

def step1(vram, req, extra="", template_name="step1"):
    return fill(tpl[template_name], MIN_VRAM_GIB=str(vram), REQUIREMENT=req, EXTRA=extra)

def save(path, nb):
    nb["metadata"] = METADATA(Path(path).name)
    nb["nbformat"], nb["nbformat_minor"] = 4, 5
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(nb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

ACCESS_LINE = "- **访问方式**：使用 Google Colab 官方内置端口代理（`proxyPort`）在浏览器直接打开工作台，绑定当前 Google 账号鉴权，无需外部隧道或密码，不开放外部 API"

# 1. SeedVR2 (Headless ComfyUI Worker + Web Studio)
seed_path = "notebooks/seedvr2/SeedVR2.ipynb"
seed_nb = json.loads(Path(seed_path).read_text(encoding="utf-8"))
seed_cells = seed_nb["cells"]
seed_rel = RELEASE_MANIFEST["apps"]["seedvr2"]
seed_code3, seed_md3 = step3_comfy_app("seedvr2", md_template=MD3_SEEDVR2)

set_source(seed_cells[0], f"""# SeedVR2（现代 Web 视频与图片 4K 超分工作台）

- **支持显卡**：40GB 及以上显存显卡（`A100 40GB / 80GB`、`H100 80GB`、`RTX 6000 96GB`）
- **单页双模态超分**：在同一工作台切换视频超分（`7B Sharp` / `3B Fast`）与图片超分；可指定 4K 目标尺寸，实际尺寸取决于原图和放大策略
- **后处理与显存控制**：内置 **CIELAB / Wavelet / AdaIN** 色彩对齐、**Split Latent** 时间分块（支持单帧 / `4n+1` 分块与 Hann 窗融合）、**Tiled VAE** 编解码与 **同屏 A/B 卷帘对比**；保留原声内容，但音轨随成片重新编码，不保证位流无损
{ACCESS_LINE}
- **执行顺序**：`1. 环境检测` → `2. 安装内部推理引擎与 Web 工作台` → `3. 下载并校验 SeedVR2 双规格权重与 VAE` → `4. 启动 Web 工作台`
""", False)
set_source(seed_cells[1], MD1.format(req="支持 `A100`、`H100`、`RTX 6000`，显存 40GB 及以上。"), False)
set_source(seed_cells[2], step1(35, REQ40), True)
set_source(seed_cells[3], MD2_COMFY_APP.format(archive=seed_rel["archive"], tag=RELEASE_MANIFEST["release_tag"]), False)
set_source(seed_cells[4], fill(tpl["step2_comfy_app"],
    RELEASE_REPO=RELEASE_MANIFEST["repo"],
    RELEASE_TAG=RELEASE_MANIFEST["release_tag"],
    APP_ARCHIVE=seed_rel["archive"],
    APP_SHA256=seed_rel["sha256"],
    BUNDLED_NODES_REL="",
    NODE_CONSTANTS="",
    EXTRA_PACKAGES='["av>=19.0.1"]',
    NODE_INSTALL='REQUIREMENT_FILES = [COMFY_DIR / "requirements.txt"]\n',
    NODE_SUMMARY=""), True)
set_source(seed_cells[5], seed_md3, False)
set_source(seed_cells[6], seed_code3, True)
set_source(seed_cells[7], MD4_APP, False)
set_source(seed_cells[8], fill(tpl["step4_comfy_app"],
    FEATURE_NAME="seedvr2",
    BUNDLED_NODES_REL="",
    LAUNCH_ARGS="",
    REQUIRED_NODES='{"SeedVR2Preprocess", "SeedVR2PostProcessing", "SeedVR2Conditioning", "SeedVR2TemporalChunk", "SeedVR2TemporalMerge", "ResizeImageMaskNode", "SaveVideo"}',
    HELPERS=HELPERS,
    LAUNCHER_SOURCE="\n" + tpl["comfy_launcher"]), True)
save(seed_path, seed_nb)
print("updated", seed_path)

# 2. MiniMax-H3 (Headless ComfyUI Worker + Web Studio)
h3_path = "notebooks/minimax-h3/MiniMaxH3.ipynb"
h3_nb = json.loads(Path(h3_path).read_text(encoding="utf-8"))
h3_cells = h3_nb["cells"]
h3_rel = RELEASE_MANIFEST["apps"]["minimax-h3"]
h3_code3, h3_md3 = step3_comfy_app("minimax-h3")

set_source(h3_cells[0], f"""# MiniMax-H3（现代 Web 音画视频工作台 + Turbo 极速加速）

- **支持显卡**：80GB 及以上显存显卡（`A100 80GB` / `H100 80GB` / `RTX 6000 96GB`）
- **单页全能融合**：音画同生文生视频（`t2v`）、单首帧或首尾帧图生视频（`fl2v`）、多模态参考生视频（`r2v`，最多 9 张图片、3 段视频、3 段独立音频，合计最多 12 个文件；视频原声不另计），无需导入或切换 `.json` 工作流
- **分辨率说明**：当前使用 H3-Base 原生 `768p`；`540p` 为低清试跑，自定义宽高为实验性画布，未接入官方 `H3-Regenerate-2K` 高分辨率再生成或超分流程
- **Turbo 极速与热加载**：内置官方 **FL2V 8 步 Turbo** 与 **Ref2V 4 步 Turbo** 一键切换，并支持从 Hugging Face 或 Civitai / HTTPS 在线热挂载自定义 `.safetensors` LoRA
{ACCESS_LINE}
- **执行顺序**：`1. 环境检测` → `2. 安装内部推理引擎与 Web 工作台` → `3. 下载并校验基础模型权重` → `4. 启动 Web 工作台`
""", False)
set_source(h3_cells[1], MD1.format(req="支持 `A100 80GB`、`H100 80GB`、`RTX 6000 96GB`，显存 80GB 及以上。"), False)
set_source(h3_cells[2], step1(70, REQ80), True)
set_source(h3_cells[3], MD2_COMFY_APP.format(archive=h3_rel["archive"], tag=RELEASE_MANIFEST["release_tag"]), False)
set_source(h3_cells[4], fill(tpl["step2_comfy_app"],
    RELEASE_REPO=RELEASE_MANIFEST["repo"],
    RELEASE_TAG=RELEASE_MANIFEST["release_tag"],
    APP_ARCHIVE=h3_rel["archive"],
    APP_SHA256=h3_rel["sha256"],
    BUNDLED_NODES_REL="",
    NODE_CONSTANTS="",
    EXTRA_PACKAGES='["av>=19.0.1"]',
    NODE_INSTALL='REQUIREMENT_FILES = [COMFY_DIR / "requirements.txt"]\n',
    NODE_SUMMARY=""), True)
set_source(h3_cells[5], h3_md3, False)
set_source(h3_cells[6], h3_code3, True)
set_source(h3_cells[7], MD4_APP, False)
set_source(h3_cells[8], fill(tpl["step4_comfy_app"],
    FEATURE_NAME="minimax-h3",
    BUNDLED_NODES_REL="",
    LAUNCH_ARGS='    "--vram-headroom", "4",\n    "--use-pytorch-cross-attention",\n',
    REQUIRED_NODES='{"MiniMaxH3ImageToVideo", "MiniMaxH3ReferenceToVideo", "MiniMaxH3AddGuide", "MiniMaxH3SigmaShift", "VAEDecodeAudio", "CreateVideo", "SaveVideo"}',
    HELPERS=HELPERS,
    LAUNCHER_SOURCE="\n" + tpl["comfy_launcher"]), True)
save(h3_path, h3_nb)
print("updated", h3_path)

# 3. Qwen-Image 2.1 (Headless ComfyUI Worker + Web Studio + Dynamic LoRA Loader)
qwen_img_path = "notebooks/qwen-image-2.1/Qwen_Image_2.1.ipynb"
qwen_img_nb = json.loads(Path(qwen_img_path).read_text(encoding="utf-8"))
qwen_img_cells = qwen_img_nb["cells"]
qwen_img_rel = RELEASE_MANIFEST["apps"]["qwen-image-2.1"]
qwen_code3, qwen_md3 = step3_comfy_app("qwen-image-2.1")

set_source(qwen_img_cells[0], f"""# Qwen-Image 2.1（现代 Web 工作台 + 在线 LoRA 热挂载）

- **推荐显卡**：80GB 级显卡（A100 80GB / H100 80GB / RTX 6000 96GB）畅跑 2K BF16 多图融合；40GB A100 亦可通过工作台 `KV 缓存 CPU 预取` / `FP8` 模式运行
- **单页全能融合**：原生 2K 与 1K 文生图、单图指令编辑、双图融合、最多 10 图参考组合、透明参考图 Alpha 保留、A/B 卷帘原图对比与一键继续精修
- **动态 LoRA 热加载**：内置精选 `Anime Consistency` 一键拉取，并支持输入任意 Hugging Face 仓库或 Civitai / HTTPS `.safetensors` 链接在后台自动校验并挂载（支持最多 6 层叠加）
{ACCESS_LINE}
- **执行顺序**：`1. 环境检测` → `2. 安装内部推理引擎与 Web 工作台` → `3. 下载并校验基础模型权重` → `4. 启动 Web 工作台`
""", False)
set_source(qwen_img_cells[1], MD1.format(req="推荐 80GB 级显卡（`A100 80GB`、`H100`、`RTX 6000`），亦兼容 `A100 40GB`。"), False)
set_source(
    qwen_img_cells[2],
    step1(
        35,
        REQ40,
        'if vram_gib < 70:\n    print("[Note] <70 GiB VRAM detected (40GB tier): keep default KV cache CPU prefetch enabled or use UNet FP8 for 2K multi-image edits.")\n',
    ),
    True,
)
set_source(qwen_img_cells[3], MD2_COMFY_APP.format(archive=qwen_img_rel["archive"], tag=RELEASE_MANIFEST["release_tag"]), False)
set_source(qwen_img_cells[4], fill(tpl["step2_comfy_app"],
    RELEASE_REPO=RELEASE_MANIFEST["repo"],
    RELEASE_TAG=RELEASE_MANIFEST["release_tag"],
    APP_ARCHIVE=qwen_img_rel["archive"],
    APP_SHA256=qwen_img_rel["sha256"],
    BUNDLED_NODES_REL="",
    NODE_CONSTANTS="",
    EXTRA_PACKAGES="[]",
    NODE_INSTALL='REQUIREMENT_FILES = [COMFY_DIR / "requirements.txt"]\n',
    NODE_SUMMARY=""), True)
set_source(qwen_img_cells[5], qwen_md3, False)
set_source(qwen_img_cells[6], qwen_code3, True)
set_source(qwen_img_cells[7], MD4_APP, False)
set_source(qwen_img_cells[8], fill(tpl["step4_comfy_app"],
    FEATURE_NAME="qwen-image-2.1",
    BUNDLED_NODES_REL="",
    LAUNCH_ARGS="",
    REQUIRED_NODES='{"TextEncodeQwenImage21", "QwenImage21Cache", "JoinImageWithAlpha", "LoraLoaderModelOnly"}',
    HELPERS=HELPERS,
    LAUNCHER_SOURCE="\n" + tpl["comfy_launcher"]), True)
save(qwen_img_path, qwen_img_nb)
print("updated", qwen_img_path)

# 4. IndexTTS 2.5 (Native Engine + Web Studio)
indextts_path = "notebooks/indextts-2.5/IndexTTS_2.5.ipynb"
indextts_nb = json.loads(Path(indextts_path).read_text(encoding="utf-8"))
indextts_cells = indextts_nb["cells"]
indextts_rel = RELEASE_MANIFEST["apps"]["indextts-2.5"]
indextts_c3 = STEP3["indextts-2.5"]
indextts_total = sum(size for _, _, size in indextts_c3["files"])

set_source(indextts_cells[0], f"""# IndexTTS 2.5（现代 Web 语音合成工作台）

- **支持显卡**：A100 (40GB / 80GB)、H100 (80GB)、RTX 6000 (96GB)
- **底层引擎**：官方原生 `index-tts`（零 ComfyUI 依赖，BF16 推理，含 QwenEmotion）
- **单页多合一能力**：零样本多语种克隆（`zh / en / ja / es / ar`）、语速调节、自然语言情绪描述或情绪参考音频、试听与会话历史回溯
{ACCESS_LINE}
- **执行顺序**：`1. 环境检测` → `2. 安装 IndexTTS 2.5 引擎与 Web 工作台` → `3. 下载 IndexTTS 2.5 模型权重` → `4. 启动 Web 工作台`
""", False)
set_source(indextts_cells[1], MD1.format(req="支持 `A100`、`H100`、`RTX 6000`，显存 40GB 及以上。"), False)
set_source(indextts_cells[2], step1(35, REQ40), True)
set_source(indextts_cells[3], MD2_INDEXTTS.format(archive=indextts_rel["archive"], tag=RELEASE_MANIFEST["release_tag"]), False)
set_source(indextts_cells[4], fill(tpl["step2_indextts"],
    RELEASE_REPO=RELEASE_MANIFEST["repo"],
    RELEASE_TAG=RELEASE_MANIFEST["release_tag"],
    APP_ARCHIVE=indextts_rel["archive"],
    APP_SHA256=indextts_rel["sha256"]), True)
set_source(indextts_cells[5], MD3_INDEXTTS.format(
    models=f"{indextts_c3['models']}（约 {indextts_total / 1024**3:.1f} GB）",
    model_dir=indextts_c3["model_dir"]), False)
set_source(indextts_cells[6], fill(tpl["step3_indextts"],
    MODEL_SOURCES=f'INDEXTTS = ({json.dumps(INDEXTTS[1])}, {json.dumps(INDEXTTS[2])}, {json.dumps(INDEXTTS[3])})',
    MODEL_FILES="".join(f'    (*{s[0]}, {json.dumps(f)}, {size}),\n' for s, f, size in indextts_c3["files"])), True)
set_source(indextts_cells[7], MD4_APP, False)
set_source(indextts_cells[8], fill(tpl["step4_app"],
    FEATURE_NAME="indextts-2.5",
    HELPERS=HELPERS,
    EXTRA_ENV='    "INDEXTTS_SRC_DIR": "/content/index-tts",\n    "INDEXTTS_MODEL_DIR": "/content/models/IndexTTS-2.5",\n'), True)
save(indextts_path, indextts_nb)
print("updated", indextts_path)

# 5. Qwen3.8-27B (Native vLLM + Multimodal Web Playground)
path = "notebooks/qwen3.8-27b/Qwen3.8_27B.ipynb"
nb = json.loads(Path(path).read_text(encoding="utf-8"))
cells = nb["cells"]
qwen38_rel = RELEASE_MANIFEST["apps"]["qwen3.8-27b"]
set_source(cells[1], MD1.format(req="支持 `A100`、`H100`、`RTX 6000`，显存 40GB 及以上。"), False)
set_source(cells[2], step1(35, REQ40, 'if vram_gib < 70:\n    print("[Note] 40GB-class GPU detected: Step 3 will automatically select Qwen3.8-27B-FP8.")\n'), True)
set_source(cells[0], f"""# Qwen3.8-27B（现代多模态深度思考 Web 工作台）

- **支持显卡**：A100 (40GB / 80GB)、H100 (80GB)、RTX 6000 (96GB)
- **底层引擎**：原生 `vLLM 0.32.0`（80GB 显卡加载 [`Qwen/Qwen3.8-27B`](https://huggingface.co/Qwen/Qwen3.8-27B) BF16，40GB 显卡加载 FP8；`262144` 上下文 + MTP 投机解码）
- **单页全能能力**：多轮图像/视频多模态对话、实时可折叠 `<think>` 深度思考流、全采样超参调节与机器资源实时监控
{ACCESS_LINE}
- **执行顺序**：`1. 环境检测` → `2. 安装 vLLM 推理引擎与 Web 工作台` → `3. 下载并校验 Qwen3.8-27B 模型权重` → `4. 启动多模态对话 Web 工作台`
""", False)
set_source(cells[3], MD2_VLLM.format(archive=qwen38_rel["archive"], tag=RELEASE_MANIFEST["release_tag"]), False)
set_source(cells[4], fill(tpl["step2_vllm"],
    RELEASE_REPO=RELEASE_MANIFEST["repo"],
    RELEASE_TAG=RELEASE_MANIFEST["release_tag"],
    APP_ARCHIVE=qwen38_rel["archive"],
    APP_SHA256=qwen38_rel["sha256"]), True)
set_source(cells[5], MD3_VLLM, False)
set_source(cells[6], tpl["step3_vllm"], True)
set_source(cells[7], MD4_VLLM, False)
set_source(cells[8], fill(tpl["step4_vllm"], HELPERS=HELPERS), True)
save(path, nb)
print("updated", path)

# 6. H3 Character Swap (Bilingual EN-primary + CN notes · MiniMax-H3 Ref2VA + Turbo8 + Character Swap LoRA V1.5 + SAM 3.1)
def _make_bilingual_swap_skeleton():
    return {
        "cells": [
            {"cell_type": "markdown", "id": "h3-swap-md0", "metadata": {"id": "h3-swap-md0"}, "source": []},
            {"cell_type": "markdown", "id": "h3-swap-md1", "metadata": {"id": "h3-swap-md1"}, "source": []},
            {"cell_type": "code", "execution_count": None, "id": "h3-swap-1", "metadata": {"id": "h3-swap-1", "cellView": "form"}, "outputs": [], "source": []},
            {"cell_type": "markdown", "id": "h3-swap-md2", "metadata": {"id": "h3-swap-md2"}, "source": []},
            {"cell_type": "code", "execution_count": None, "id": "h3-swap-2", "metadata": {"id": "h3-swap-2", "cellView": "form"}, "outputs": [], "source": []},
            {"cell_type": "markdown", "id": "h3-swap-md3", "metadata": {"id": "h3-swap-md3"}, "source": []},
            {"cell_type": "code", "execution_count": None, "id": "h3-swap-3", "metadata": {"id": "h3-swap-3", "cellView": "form"}, "outputs": [], "source": []},
            {"cell_type": "markdown", "id": "h3-swap-md4", "metadata": {"id": "h3-swap-md4"}, "source": []},
            {"cell_type": "code", "execution_count": None, "id": "h3-swap-4", "metadata": {"id": "h3-swap-4", "cellView": "form"}, "outputs": [], "source": []},
        ],
        "metadata": METADATA("H3_Character_Swap.ipynb"),
        "nbformat": 4,
        "nbformat_minor": 5,
    }

swap_path = "notebooks/h3-character-swap/H3_Character_Swap.ipynb"
swap_nb = json.loads(Path(swap_path).read_text(encoding="utf-8")) if Path(swap_path).is_file() else _make_bilingual_swap_skeleton()
swap_cells = swap_nb["cells"]
swap_rel = RELEASE_MANIFEST["apps"]["h3-character-swap"]
swap_md3_tpl = """### 3. Download & Verify Model Weights · 下载并校验模型权重
- **What this does**: Downloads pinned weights{models} into `{model_dir}` using high-speed `hf_xet` transfers and exact byte-size checks.
- **中文说明**：使用 `hf_xet` 高速下载并精确校验 `MiniMax-H3 Ref2VA (INT8)`、`FL2V Turbo 8-step`、`Character Swap LoRA V1.5`、`SAM 3.1 Multiplex`、`Qwen3-VL-32B-INT8` 与双模态 VAE（共约 53.8 GiB）。
- **Run**: Execute once; existing verified files are reused automatically."""
swap_code3, swap_md3 = step3_comfy_app("h3-character-swap", md_template=swap_md3_tpl, english_units=True)

set_source(swap_cells[0], f"""# H3 Character Swap (Character & Multi-Person Video Replacement Web Studio)

> Bilingual Colab Launcher (**English-primary** with Chinese quick notes · 主英文说明，关键参数附中文注释)

- **Recommended GPUs / 显存要求**: `A100 80GB` / `H100 80GB` / `RTX 6000 96GB` for `736p` & full-speed inference; `A100 40GB` is also supported at `480p` (`832×480`, recommended `5s` clips first).
- **Powered by `MiniMax-H3 Ref2VA INT8 + FL2V Turbo 8-step + Character Swap V1.5 + SAM 3.1`**: Replaces a character or multiple people directly from a source performance video (`<Video 1>`) and standalone character reference photos (`<Picture 1..N>`) via stock `MiniMaxH3ReferenceToVideo` + automatic `SAM 3.1` subject tracking & edit mask + 8-step `er_sde` sampling — locking background pixels and redrawing full head/outfit identity while preserving motion and soundtrack.
- **关键能力说明（人物替换与多人物替换）**：同一页面支持 **人物替换** 与 **多人物替换**（支持 1–4 位角色），内置 `SAM 3.1` 自动人物分割跟踪与 64px 遮罩外扩（无需手绘遮罩，背景完全锁定，完整替换人物脸型与全身服饰），支持可选关键帧锚点引导（`Anchor Guide`）与 5 帧历史无缝接续，并保留原视频音轨。
- **Browser Access / 浏览器访问**: Uses **Google Colab Native Proxy** (`google.colab.kernel.proxyPort`) directly in your signed-in browser session — no password setup, no external tunnel, and no external API exposed; expires when the runtime stops.
- **Execution Order / 执行顺序**: `1. Environment Check` → `2. Install Engine & Web Bundle` → `3. Download Model Weights` → `4. Launch Web Studio`
""", False)
set_source(swap_cells[1], """### 1. Environment Check · 环境检测
- **What this does**: Verifies CUDA GPU model, VRAM, BF16 support, system RAM, and free disk space under `/content`.
- **中文说明**：检测 GPU 型号（推荐 `A100 80GB` / `H100` / `RTX 6000`，亦兼容 `40GB A100` 运行 `480p`）、可用磁盘空间与 BF16 支持。
- **Run**: Execute cell and wait for `[OK]`.""", False)
set_source(swap_cells[2], step1(
    35,
    "40GB+ VRAM (A100 40GB/80GB, H100 80GB, RTX 6000 96GB)",
    'if vram_gib < 70:\n    print("[Note] <70 GiB VRAM detected (40GB tier): use 480p resolution and start with 5s test clips first.")\n',
    template_name="step1",
), True)
set_source(swap_cells[3], f"""### 2. Install Inference Engine & App Bundle · 安装推理引擎与应用包
- **What this does**: Checks out pinned ComfyUI (`v0.43.2`), installs `av>=19.0.1` + Web Studio deps, verifies & extracts `{swap_rel["archive"]}` (`{RELEASE_MANIFEST["release_tag"]}`), and syncs the bundled `ComfyUI-H3-Swap-Mask` helper nodes.
- **中文说明**：安装固定版本内部无头 ComfyUI 引擎并拉取校验 Release 前端与后端应用包，同步内置 `ComfyUI-H3-Swap-Mask` 遮罩辅助节点。
- **Run**: Execute cell and wait for `[OK]`.""", False)
set_source(swap_cells[4], fill(tpl["step2_comfy_app"],
    RELEASE_REPO=RELEASE_MANIFEST["repo"],
    RELEASE_TAG=RELEASE_MANIFEST["release_tag"],
    APP_ARCHIVE=swap_rel["archive"],
    APP_SHA256=swap_rel["sha256"],
    BUNDLED_NODES_REL="backend/features/h3_character_swap/comfy_nodes",
    NODE_CONSTANTS="",
    EXTRA_PACKAGES='["av>=19.0.1"]',
    NODE_INSTALL='REQUIREMENT_FILES = [COMFY_DIR / "requirements.txt"]\n',
    NODE_SUMMARY=" + H3-Swap-Mask"), True)
set_source(swap_cells[5], swap_md3, False)
set_source(swap_cells[6], swap_code3, True)
set_source(swap_cells[7], """### 4. Launch Web Studio (Colab Native Proxy) · 启动 Web 工作台（Colab 原生代理）
- **What this does**: Starts internal ComfyUI on `127.0.0.1:8189` (whitelisting `ComfyUI-H3-Swap-Mask`), launches Web Studio on `127.0.0.1:8188`, and opens it through Google Colab's native browser proxy.
- **中文说明**：后台启动 ComfyUI 推理引擎与 Web 工作台，并通过 Colab 原生端口代理生成仅当前 Google 账号可打开的浏览器入口（无需密码、无 Cloudflare 隧道、不开放外部 API）。
- **Run**: Execute inside your browser Colab notebook and click the opened window link.""", False)
set_source(swap_cells[8], fill(tpl["step4_comfy_app"],
    FEATURE_NAME="h3-character-swap",
    BUNDLED_NODES_REL="backend/features/h3_character_swap/comfy_nodes",
    LAUNCH_ARGS='    "--vram-headroom", "4",\n    "--use-pytorch-cross-attention",\n    "--whitelist-custom-nodes", "ComfyUI-H3-Swap-Mask",\n',
    REQUIRED_NODES='{"UNETLoader", "LoraLoaderModelOnly", "CLIPLoader", "VAELoader", "CheckpointLoaderSimple", "CLIPTextEncode", "LoadVideo", "GetVideoComponents", "LoadImage", "ImageFromBatch", "ImageScale", "VAEEncode", "SAM3_Detect", "SAM3_VideoTrack", "SAM3_TrackToMask", "H3SwapSelectMask", "H3SwapExpandMask", "H3SwapApplyEditMask", "MiniMaxH3SigmaShift", "MiniMaxH3ReferenceToVideo", "MiniMaxH3AddGuide", "RandomNoise", "BasicGuider", "KSamplerSelect", "BasicScheduler", "SamplerCustomAdvanced", "LTXVSeparateAVLatent", "VAEDecode", "CreateVideo", "SaveVideo"}',
    HELPERS=HELPERS,
    LAUNCHER_SOURCE="\n" + tpl["comfy_launcher"]), True)
save(swap_path, swap_nb)
print("updated", swap_path)

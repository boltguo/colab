"""生成 notebooks/ 下全部笔记本的第 1–4 步：python3 tools/build_notebooks.py"""
import ast, json, os, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
tpl = {p.stem: p.read_text(encoding="utf-8") for p in (ROOT / "tools/templates").glob("*.py")}
CLOUDFLARED = tpl["cloudflared"]
HELPERS = tpl["helpers"]

REQ80 = "80GB 级显存（A100 80GB / H100 80GB / RTX 6000 96GB）"
REQ40 = "40GB 及以上显存（A100 40GB / 80GB、H100 80GB、RTX 6000 96GB）"

COMFY = {
    "minimax-h3": dict(path="notebooks/minimax-h3/MiniMaxH3.ipynb", vram=70, req=REQ80, md_vram="80GB 及以上",
        extra='["av>=19.0.1"]', args=['"--vram-headroom", "4",', '"--use-pytorch-cross-attention",'],
        nodes=["MiniMaxH3ImageToVideo", "MiniMaxH3ReferenceToVideo", "VAEDecodeAudio", "CreateVideo", "ComfyMathExpression", "ResolutionSelector"]),
    "qwen-image-2.1": dict(path="notebooks/qwen-image-2.1/Qwen_Image_2.1.ipynb", vram=70, req=REQ80, md_vram="80GB 及以上",
        extra="[]", args=[], nodes=["TextEncodeQwenImage21", "QwenImage21Cache", "CustomCombo", "ComfyMathExpression", "ResolutionSelector"]),
    "krea-2": dict(path="notebooks/krea-2/Krea_2.ipynb", vram=35, req=REQ40, md_vram="40GB 及以上",
        extra="[]", args=[], nodes=["TextGenerate", "TextEncodeQwenImageEditPlus", "FluxKontextMultiReferenceLatentMethod", "ResolutionSelector"]),
    "seedvr2": dict(path="notebooks/seedvr2/SeedVR2.ipynb", vram=35, req=REQ40, md_vram="40GB 及以上",
        extra="[]", args=[], nodes=["SeedVR2Preprocess", "SeedVR2PostProcessing", "SeedVR2Conditioning", "SeedVR2TemporalChunk", "SeedVR2TemporalMerge"]),
    "indextts-2.5": dict(path="notebooks/indextts-2.5/IndexTTS_2.5.ipynb", vram=35, req=REQ40, md_vram="40GB 及以上",
        extra='["transformers==4.57.6", "wetext>=0.0.9", "fugashi>=1.2.0", "unidic-lite>=1.0.0"]',
        args=['"--whitelist-custom-nodes", "ComfyUI-IndexTTS-2_5",'],
        nodes=["IndexTTS2_5Node", "EmoSettingsNode", "LoadAudio", "SaveAudioMP3"], node=True),
}

NODE_CONSTANTS = '''NODE_DIR = COMFY_DIR / "custom_nodes/ComfyUI-IndexTTS-2_5"
NODE_REPO = "https://github.com/mailzwj/ComfyUI-IndexTTS-2.5"
NODE_REVISION = "a501798540c8079530b0e03d824c79763d12e7bd"
'''
NODE_INSTALL = '''checkout_repo(NODE_DIR, NODE_REPO, NODE_REVISION, "ComfyUI-IndexTTS-2_5", allow_local_changes=True)

# 让 Linux 也走预编译的 wetext 文本规范化，避免编译 pynini
front_py = NODE_DIR / "indextts/utils/front.py"
front_py.write_text(front_py.read_text(encoding="utf-8").replace('if platform.system() != "Linux":', "if True:"), encoding="utf-8")
REQUIREMENT_FILES = [COMFY_DIR / "requirements.txt", NODE_DIR / "requirements.txt"]
'''

MD1 = """### 1. 环境检测
- **功能**：检测 GPU 型号、显存容量、BF16 支持、系统内存、磁盘空间及 PyTorch / CUDA 版本。
- **要求**：{req}
- **使用**：直接运行，输出 `[OK]` 后继续。"""
MD2_COMFY = """### 2. 安装 ComfyUI
- **功能**：安装 ComfyUI `v0.43.2`{node}、依赖与 `cloudflared` `2026.10.6`。
- **使用**：直接运行，输出 `[OK]` 后继续。"""
MD2_VLLM = """### 2. 安装 vLLM 推理引擎
- **功能**：安装 vLLM `0.32.0`、`hf_xet`、`openai` 与 `cloudflared` `2026.10.6`。
- **使用**：直接运行，输出 `[OK]` 后继续。"""
MD3_COMFY = """### 3. 下载模型与工作流
- **功能**：下载{models}至 `{model_dir}`，同步工作流至 `/content/ComfyUI/user/default/workflows`。
- **使用**：直接运行，输出 `[OK]` 后继续。"""
MD3_VLLM = """### 3. 下载 Qwen3.8-27B 模型
- **功能**：按显存下载模型至 `/content/models`：80GB 及以上为 `Qwen/Qwen3.8-27B` BF16（约 55 GB），40GB 为 `Qwen/Qwen3.8-27B-FP8`（约 28 GB）。
- **使用**：直接运行，输出 `[OK]` 后继续。"""
SECRET = "- **要求**：在 Colab 左侧 **🔑 Secrets** 中添加 `CF_TUNNEL_TOKEN` 并开启访问权限。"
MD4_COMFY = f"""### 4. 启动并打开 ComfyUI
- **功能**：后台启动 ComfyUI（`127.0.0.1:8188`），读取 `CF_TUNNEL_TOKEN` 启动 Cloudflare Tunnel 并检查公网访问。
{SECRET}
- **使用**：直接运行，通过 Cloudflare 绑定的域名访问。"""
MD4_VLLM = f"""### 4. 启动并挂载 API 服务
- **功能**：后台启动 `vllm serve`（`127.0.0.1:8188`，`262144` 上下文，MTP 投机采样），读取 `CF_TUNNEL_TOKEN` 启动 Cloudflare Tunnel 并检查公网访问，提供 OpenAI（`/v1/chat/completions`）与 Anthropic（`/v1/messages`）接口。
{SECRET}
- **使用**：直接运行，输出 Claude Code 与 OpenAI 调用配置。"""

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
QWEN_LORA = ("QWEN_LORA", "WarmBloodAban/Qwen-Image-2.1-LoRAs", "c4ab5473bfdf585fc19cfd1e280f79d2b0c79947", "loras")
KREA = ("KREA", "Comfy-Org/Krea-2", "1171f4dc7e325bf3734586942e737872506c73e1", "")
SEEDVR2 = ("SEEDVR2", "Comfy-Org/SeedVR2", "df48879708206a403d2a61acd55578c2e80fd233", "")
INDEXTTS = ("INDEXTTS", "IndexTeam/IndexTTS-2.5", "c39ce5ba981572cb187443877ff559dfb246ce63", "TTS/IndexTTS-2.5")

STEP3 = {
    "minimax-h3": dict(models=" MiniMax H3 FL2VA / Ref2VA 主模型、文本编码器、VAE 与 Turbo LoRA", files=[
        (H3, "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors", 20970379616),
        (H3, "diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors", 20970379616),
        (H3, "text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors", 27141342152),
        (H3, "vae/minimax_h3_video_vae_int8_convrot.safetensors", 2811065184),
        (H3, "vae/minimax_h3_audio_vae_fp32.safetensors", 605254808),
        (H3, "loras/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors", 1956193000),
        (TURBO, "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors", 1956193000),
    ]),
    "qwen-image-2.1": dict(models=" Qwen-Image 2.1 BF16 权重与动漫一致性 LoRA", files=[
        (QWEN, "diffusion_models/qwen_image_2.1_bf16.safetensors", 14230280616),
        (QWEN, "text_encoders/qwen3vl_8b_bf16.safetensors", 17534334616),
        (QWEN, "vae/qwen_image_2.1_vae_bf16.safetensors", 675509688),
        (QWEN_LORA, "Qwen2.1_Anime_consistency.safetensors", 167830408),
    ]),
    "krea-2": dict(models=" Krea 2 BF16 权重与 10 款官方风格 / 参考图 LoRA", files=[
        (KREA, "diffusion_models/krea2_turbo_bf16.safetensors", 26283332608),
        (KREA, "text_encoders/qwen3vl_4b_bf16.safetensors", 8875719384),
        (KREA, "vae/qwen_image_vae.safetensors", 253806246),
        (KREA, "loras/krea2_style_reference.safetensors", 457111760),
        *[(KREA, f"loras/krea2_{n}.safetensors", 469291992) for n in
          ["retroanime", "darkbrush", "rainywindow", "softwatercolor", "sunsetblur", "vintagetarot", "neondrip", "dotmatrix", "kidsdrawing"]],
    ]),
    "seedvr2": dict(models=" SeedVR2 FP16 `7B Sharp`、`3B` 与 VAE", files=[
        (SEEDVR2, "diffusion_models/seedvr2_7b_sharp_fp16.safetensors", 16480583960),
        (SEEDVR2, "diffusion_models/seedvr2_3b_fp16.safetensors", 6784268336),
        (SEEDVR2, "vae/seedvr2_ema_vae_fp16.safetensors", 501324814),
    ]),
    "indextts-2.5": dict(models=" IndexTTS-2.5 权重（含 QwenEmotion）与辅助编码器 / 声码器", model_dir="/content/ComfyUI/models/TTS/IndexTTS-2.5", files=[
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
        ]], post='''import sys
NODE_DIR = COMFY_DIR / "custom_nodes/ComfyUI-IndexTTS-2_5"
if str(NODE_DIR) not in sys.path:
    sys.path.insert(0, str(NODE_DIR))
from indextts.utils.model_download import ensure_models_available
ensure_models_available(str(MODEL_DIR / "TTS/IndexTTS-2.5"))
sample_audio = NODE_DIR / "example/ref_audio.mp3"
if sample_audio.is_file() and not (COMFY_DIR / "input/ref_audio.mp3").exists():
    shutil.copy2(sample_audio, COMFY_DIR / "input/ref_audio.mp3")
    print("示例音频：", COMFY_DIR / "input/ref_audio.mp3")
'''),
}

def step3(key):
    c = STEP3[key]
    sources = []
    for source, *_ in c["files"]:
        if source not in sources:
            sources.append(source)
    total = sum(size for _, _, size in c["files"])
    text = fill(tpl["step3_comfy"],
        WORKFLOW_FOLDER=f"workflows/{key}",
        WORKFLOW_FILES="".join(f'    "{p.name}",\n' for p in sorted(Path(f"workflows/{key}").glob("*.json"))),
        MODEL_SOURCES="".join(f'{name} = ({json.dumps(repo)}, {json.dumps(rev)}, {json.dumps(folder)})\n' for name, repo, rev, folder in sources),
        MODEL_FILES="".join(f'    (*{s[0]}, {json.dumps(f)}, {size}),\n' for s, f, size in c["files"]),
        POST_DOWNLOAD=c.get("post", ""))
    md = MD3_COMFY.format(models=f"{c['models']}（约 {total / 1024**3:.1f} GB）", model_dir=c.get("model_dir", "/content/ComfyUI/models"))
    return text, md

def step1(vram, req, extra=""):
    return fill(tpl["step1"], MIN_VRAM_GIB=str(vram), REQUIREMENT=req, EXTRA=extra)

def save(path, nb):
    nb["metadata"] = METADATA(Path(path).name)
    nb["nbformat"], nb["nbformat_minor"] = 4, 5
    Path(path).write_text(json.dumps(nb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

for key, c in COMFY.items():
    nb = json.loads(Path(c["path"]).read_text(encoding="utf-8"))
    cells = nb["cells"]
    node = c.get("node")
    set_source(cells[1], MD1.format(req=f"支持 `A100`、`H100`、`RTX 6000`，显存 {c['md_vram']}。"), False)
    set_source(cells[2], step1(c["vram"], c["req"]), True)
    set_source(cells[3], MD2_COMFY.format(node="、`ComfyUI-IndexTTS-2.5` 节点" if node else ""), False)
    set_source(cells[4], fill(tpl["step2_comfy"],
        NODE_CONSTANTS=NODE_CONSTANTS if node else "",
        EXTRA_PACKAGES=c["extra"],
        NODE_INSTALL=NODE_INSTALL if node else 'REQUIREMENT_FILES = [COMFY_DIR / "requirements.txt"]\n',
        CLOUDFLARED=CLOUDFLARED,
        NODE_SUMMARY=" | ComfyUI-IndexTTS-2.5: {NODE_REVISION[:12]}" if node else ""), True)
    code3, md3 = step3(key)
    set_source(cells[5], md3, False)
    set_source(cells[6], code3, True)
    set_source(cells[7], MD4_COMFY, False)
    set_source(cells[8], fill(tpl["step4_comfy"],
        LAUNCH_ARGS="".join(f"    {a}\n" for a in c["args"]),
        REQUIRED_NODES="{" + ", ".join(json.dumps(n) for n in c["nodes"]) + "}",
        HELPERS=HELPERS, LAUNCHER_SOURCE="\n" + tpl["comfy_launcher"]), True)
    save(c["path"], nb)
    print("updated", c["path"])

path = "notebooks/qwen3.8-27b/Qwen3.8_27B.ipynb"
nb = json.loads(Path(path).read_text(encoding="utf-8"))
cells = nb["cells"]
set_source(cells[1], MD1.format(req="支持 `A100`、`H100`、`RTX 6000`，显存 40GB 及以上。"), False)
set_source(cells[2], step1(35, REQ40, 'if vram_gib < 70:\n    print("[提示] 40GB 级显卡，第 3 步使用 FP8 模型。")\n'), True)
set_source(cells[0], """# Qwen3.8-27B（原生全精度多模态 API 服务）

- **支持显卡**：A100 (40GB / 80GB)、H100 (80GB)、RTX 6000 (96GB)
- **默认配置**：[`Qwen/Qwen3.8-27B`](https://huggingface.co/Qwen/Qwen3.8-27B) BF16（40GB 显卡使用 FP8）、256K（`262144`）上下文、图像 / 视频理解、`reasoning_effort` 与工具调用
- **访问方式**：通过 Colab Secrets 自动读取 `CF_TUNNEL_TOKEN`，挂载 Cloudflare Tunnel 直连自有域名与 API
- **执行顺序**：`1. 环境检测` → `2. 安装 vLLM 推理引擎` → `3. 下载 Qwen3.8-27B 模型` → `4. 启动并挂载 API 服务`

| 接口路径 | 协议 | 客户端 |
| --- | --- | --- |
| `POST /v1/messages` | Anthropic Messages | Claude Code |
| `POST /v1/chat/completions` | OpenAI Chat Completions | OpenAI SDK、Cursor、Cline |
| `GET /v1/models` | OpenAI / Anthropic Models | 模型名 `Qwen/Qwen3.8-27B` 或 `qwen3.8-27b` |
""", False)
set_source(cells[3], MD2_VLLM, False)
set_source(cells[4], fill(tpl["step2_vllm"], CLOUDFLARED=CLOUDFLARED), True)
set_source(cells[5], MD3_VLLM, False)
set_source(cells[6], tpl["step3_vllm"], True)
set_source(cells[7], MD4_VLLM, False)
set_source(cells[8], fill(tpl["step4_vllm"], HELPERS=HELPERS), True)
save(path, nb)
print("updated", path)

"""Qwen-Image 2.1 Dynamic ComfyUI Graph Builder, LoRA Orchestrator & Mock Renderer."""
import hashlib
import math
import os
from pathlib import Path
import secrets
import shutil
import struct
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid
import zlib

from ...core.comfy_client import ComfyClient
from ...core.lora_manager import CuratedLoraSpec, LoraDownloadRequest, LoraManager
from ...core.security import ensure_safe_dir, ensure_safe_path
from ...core.storage import MediaStorage
from .schemas import (
    GeneratedImageItem,
    ImageOutputFormat,
    QwenImageGenerateRequest,
    QwenImageResult,
    compute_preset_dimensions,
    snap32,
)

ProgressFn = Callable[[float, str], None]

UNET_FILENAME = "qwen_image_2.1_bf16.safetensors"
CLIP_FILENAME = "qwen3vl_8b_bf16.safetensors"
VAE_FILENAME = "qwen_image_2.1_vae_bf16.safetensors"

CURATED_QWEN_LORAS: List[CuratedLoraSpec] = [
    CuratedLoraSpec(
        id="anime_consistency",
        filename="Qwen2.1_Anime_consistency.safetensors",
        label="二次元角色一致性 (Anime Consistency)",
        description="强化动漫/插画画风下的人物五官、服饰与线条一致性，文生图与参考图换装均适用。",
        repo_id="WarmBloodAban/Qwen-Image-2.1-LoRAs",
        revision="c4ab5473bfdf585fc19cfd1e280f79d2b0c79947",
        repo_filename="Qwen2.1_Anime_consistency.safetensors",
        expected_size=167830408,
        recommended_strength=0.85,
        trigger_words=("anime style", "consistent character"),
        tags=("官方精选", "角色一致性", "二次元"),
    ),
]


def _write_pure_png(
    dest: Path,
    width: int,
    height: int,
    palette_seed: int,
    variant: str = "studio",
) -> Tuple[int, int]:
    """Zero-dependency pure-stdlib PNG generator for demo presets & fallback mock previews."""
    w = max(64, min(1024, width))
    h = max(64, min(1024, height))

    if variant == "subject":
        c1, c2, accent = (241, 245, 249), (219, 234, 254), (37, 99, 235)
    elif variant == "scene":
        c1, c2, accent = (254, 243, 199), (254, 202, 202), (217, 119, 6)
    else:
        r_off = (palette_seed * 37) % 50
        g_off = (palette_seed * 73) % 50
        b_off = (palette_seed * 19) % 50
        c1 = (232 - r_off // 3, 240 - g_off // 4, 252 - b_off // 5)
        c2 = (196 + r_off // 2, 218 + g_off // 3, 248 - b_off // 3)
        accent = (37 + r_off, 99 + g_off // 2, 225 - b_off // 2)

    cx, cy = w * 0.5, h * 0.5
    radius = min(w, h) * 0.24
    rows = bytearray()
    for y in range(h):
        rows.append(0)  # filter type 0
        ty = y / max(1, h - 1)
        base_r = int(c1[0] * (1.0 - ty) + c2[0] * ty)
        base_g = int(c1[1] * (1.0 - ty) + c2[1] * ty)
        base_b = int(c1[2] * (1.0 - ty) + c2[2] * ty)
        dy2 = (y - cy) ** 2
        grid_y = (y % 64) == 0
        for x in range(w):
            dist = math.sqrt((x - cx) ** 2 + dy2)
            if abs(dist - radius) < 3.5:
                r, g, b = accent
            elif dist < radius:
                blend = 0.28 * (1.0 - dist / max(1.0, radius))
                r = int(base_r * (1.0 - blend) + accent[0] * blend)
                g = int(base_g * (1.0 - blend) + accent[1] * blend)
                b = int(base_b * (1.0 - blend) + accent[2] * blend)
            elif grid_y or (x % 64) == 0:
                r, g, b = max(0, base_r - 10), max(0, base_g - 10), max(0, base_b - 8)
            else:
                r, g, b = base_r, base_g, base_b
            rows.extend((max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))))

    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", crc)

    ihdr = struct.pack("!IIBBBBB", w, h, 8, 2, 0, 0, 0)
    compressed = zlib.compress(bytes(rows), level=4)
    png_bytes = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", compressed) + _chunk(b"IEND", b"")
    dest.write_bytes(png_bytes)
    return w, h


def _render_mock_canvas(
    dest: Path,
    *,
    width: int,
    height: int,
    fmt: ImageOutputFormat,
    quality: int,
    seed: int,
    mode: str,
    prompt: str,
    loras: List[Dict[str, Any]],
    ref_paths: List[Path],
) -> Tuple[int, int]:
    """Render a rich visual preview image in --mock mode (uses Pillow when available, else pure PNG)."""
    # Cap mock pixel dimensions slightly so instant local UI previews stay snappy (<150ms)
    scale = min(1.0, 1280.0 / max(width, height))
    out_w = max(256, int(round((width * scale) / 8.0) * 8))
    out_h = max(256, int(round((height * scale) / 8.0) * 8))

    try:
        from PIL import Image, ImageDraw  # type: ignore

        img = Image.new("RGB", (out_w, out_h), (240, 245, 252))
        draw = ImageDraw.Draw(img)

        h_hash = int(hashlib.sha256(f"{seed}:{prompt}:{mode}".encode("utf-8")).hexdigest()[:8], 16)
        top_c = (226 + (h_hash % 22), 236 + ((h_hash >> 4) % 16), 252)
        bot_c = (195 + ((h_hash >> 8) % 35), 216 + ((h_hash >> 12) % 28), 246)

        for y in range(out_h):
            t = y / max(1, out_h - 1)
            rc = int(top_c[0] * (1 - t) + bot_c[0] * t)
            gc = int(top_c[1] * (1 - t) + bot_c[1] * t)
            bc = int(top_c[2] * (1 - t) + bot_c[2] * t)
            draw.line([(0, y), (out_w, y)], fill=(rc, gc, bc))

        # Subtle architectural composition shapes
        cx, cy = int(out_w * 0.5), int(out_h * 0.48)
        rad = int(min(out_w, out_h) * 0.23)
        draw.ellipse(
            [cx - rad, cy - rad, cx + rad, cy + rad],
            fill=(255, 255, 255),
            outline=(37, 99, 235),
            width=4,
        )
        inner = int(rad * 0.62)
        draw.ellipse(
            [cx - inner, cy - inner, cx + inner, cy + inner],
            fill=(219, 234, 254),
            outline=(59, 130, 246),
            width=3,
        )

        # Composite reference image thumbnails in the corner when in edit mode
        thumb_x = 28
        for idx, rpath in enumerate(ref_paths[:4]):
            try:
                with Image.open(rpath) as rimg:
                    thumb = rimg.convert("RGB")
                    thumb.thumbnail((148, 148))
                    tw, th = thumb.size
                    box_y = 28
                    draw.rectangle(
                        [thumb_x - 3, box_y - 3, thumb_x + tw + 3, box_y + th + 3],
                        fill=(255, 255, 255),
                        outline=(37, 99, 235),
                        width=2,
                    )
                    img.paste(thumb, (thumb_x, box_y))
                    draw.rectangle([thumb_x, box_y, thumb_x + 70, box_y + 22], fill=(37, 99, 235))
                    draw.text((thumb_x + 6, box_y + 5), f"<image{idx + 1}>", fill=(255, 255, 255))
                    thumb_x += tw + 18
            except Exception:
                pass

        # Metadata banner at bottom
        banner_h = 96
        draw.rectangle([20, out_h - banner_h - 20, out_w - 20, out_h - 20], fill=(255, 255, 255), outline=(203, 213, 225), width=2)
        lora_txt = ", ".join(f"{it['filename']} ({it['strength_model']})" for it in loras) or "None"
        ascii_summary = (
            f"[MOCK PREVIEW] Qwen-Image 2.1  |  Mode: {mode}  |  Target: {width}x{height}  |  Seed: {seed}"
        )
        ascii_lora = f"Active LoRAs: {lora_txt[:88]}"
        draw.text((38, out_h - banner_h - 4), ascii_summary, fill=(15, 23, 42))
        draw.text((38, out_h - banner_h + 24), ascii_lora, fill=(37, 99, 235))
        draw.text((38, out_h - banner_h + 50), f"Refs: {len(ref_paths)}  |  Format: {fmt.upper()}", fill=(71, 85, 105))

        save_kwargs: Dict[str, Any] = {}
        pil_fmt = "PNG"
        if fmt == "webp":
            pil_fmt = "WEBP"
            save_kwargs["quality"] = quality
        elif fmt == "jpeg":
            pil_fmt = "JPEG"
            save_kwargs["quality"] = quality
            save_kwargs["subsampling"] = 0
        img.save(dest, format=pil_fmt, **save_kwargs)
        return width, height
    except Exception:
        fb_scale = min(1.0, 640.0 / max(width, height))
        _write_pure_png(
            dest,
            max(64, int(round(width * fb_scale))),
            max(64, int(round(height * fb_scale))),
            palette_seed=seed,
        )
        return width, height


def _convert_or_copy_image(
    src_png: Path,
    dest: Path,
    fmt: ImageOutputFormat,
    quality: int,
) -> Tuple[int, int]:
    """Read image dimensions and optionally transcode PNG -> WebP / JPEG."""
    try:
        from PIL import Image  # type: ignore

        with Image.open(src_png) as img:
            w, h = img.size
            if fmt == "png":
                shutil.copy2(src_png, dest)
            elif fmt == "webp":
                img.save(dest, format="WEBP", quality=quality, method=4)
            else:
                rgb = img.convert("RGB")
                rgb.save(dest, format="JPEG", quality=quality, subsampling=0)
            return w, h
    except ImportError:
        # Fallback if Pillow is unavailable: read PNG IHDR dimensions directly
        shutil.copy2(src_png, dest)
        w, h = 2048, 2048
        with src_png.open("rb") as f:
            sig = f.read(24)
            if len(sig) >= 24 and sig[:8] == b"\x89PNG\r\n\x1a\n":
                w, h = struct.unpack("!II", sig[16:24])
        return int(w), int(h)


class QwenImageRunner:
    def __init__(
        self,
        storage: MediaStorage,
        data_dir: Path,
        mock_mode: bool = False,
    ) -> None:
        self.storage = storage
        self.data_dir = ensure_safe_dir(data_dir)
        self.mock_mode = mock_mode

        comfy_dir = Path(os.environ.get("COMFY_DIR") or "/content/ComfyUI")
        self.comfy = ComfyClient(comfy_dir=comfy_dir)

        if not mock_mode and (comfy_dir / "models").is_dir():
            loras_dir = ensure_safe_dir(comfy_dir / "models" / "loras")
        else:
            loras_dir = ensure_safe_dir(self.data_dir / "loras", stop_at=self.data_dir)

        self.lora_manager = LoraManager(
            loras_dir=loras_dir,
            curated=CURATED_QWEN_LORAS,
            mock_mode=mock_mode,
        )

    @staticmethod
    def _probe_image_dims(path: Path) -> Tuple[int, int]:
        try:
            from PIL import Image  # type: ignore

            with Image.open(path) as im:
                return int(im.size[0]), int(im.size[1])
        except Exception:
            with path.open("rb") as f:
                sig = f.read(24)
                if len(sig) >= 24 and sig[:8] == b"\x89PNG\r\n\x1a\n":
                    w, h = struct.unpack("!II", sig[16:24])
                    return int(w), int(h)
        return 1024, 1024

    def is_ready(self) -> Tuple[bool, bool]:
        """Return (ready, loaded) tuple for /api/v1/system."""
        if self.mock_mode:
            return True, True
        up = self.comfy.is_ready(timeout=2.0)
        return up, up

    def release_vram(self) -> None:
        if self.mock_mode:
            return
        self.comfy.free_memory(unload_models=True, free_memory=True)

    def execute_task(self, raw_params: Dict[str, Any], on_progress: ProgressFn) -> Dict[str, Any]:
        """Unified TaskManager executor handling both async LoRA downloads and image generation."""
        if raw_params.get("__task_kind__") == "lora_download":
            dl_req = LoraDownloadRequest.model_validate(raw_params["payload"])
            entry = self.lora_manager.ensure_available(
                dl_req.source,
                filename=dl_req.filename,
                revision=dl_req.revision,
                token=dl_req.token,
                on_progress=on_progress,
                progress_range=(0.05, 0.98),
            )
            return {"kind": "lora_download", "lora": entry.model_dump()}

        req = QwenImageGenerateRequest.model_validate(raw_params)
        return self._run_generation(req, on_progress).model_dump()

    def _resolve_target_dimensions(
        self,
        req: QwenImageGenerateRequest,
        ref_paths: Optional[List[Path]] = None,
    ) -> Tuple[int, int, int, bool]:
        """Return (canvas_width, canvas_height, ref_encode_resolution, use_ref_latent_output)."""
        if req.resolution_tier == "original":
            ref_res = 0
        elif req.resolution_tier == "1K":
            ref_res = 1024
        else:
            ref_res = 2048

        refs = ref_paths or []
        if req.mode != "t2i" and refs and req.aspect_ratio == "match_input":
            rw, rh = self._probe_image_dims(refs[0])
            if ref_res == 0:
                w, h = snap32(rw), snap32(rh)
            else:
                ratio = rw / max(1, rh)
                w = snap32(math.sqrt(ref_res * ref_res * ratio))
                h = snap32(math.sqrt(ref_res * ref_res / ratio))
            use_ref_latent = req.reference_conditioning_mode == "vae_and_vision"
            return w, h, ref_res, use_ref_latent

        if req.aspect_ratio == "custom" or req.resolution_tier == "custom":
            w, h = snap32(req.width), snap32(req.height)
            return w, h, ref_res, False

        preset_tier = "1K" if req.resolution_tier == "1K" else "2K"
        w, h = compute_preset_dimensions(preset_tier, req.aspect_ratio)
        return w, h, ref_res, False

    def _build_comfy_graph(
        self,
        req: QwenImageGenerateRequest,
        *,
        actual_seed: int,
        staged_ref_names: List[str],
        resolved_loras: List[Dict[str, Any]],
        canvas_w: int,
        canvas_h: int,
        ref_res: int,
        kv_device: str,
        use_ref_latent: bool = False,
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str], str]:
        """Dynamically assemble the exact ComfyUI operator graph dictionary."""
        graph: Dict[str, Dict[str, Any]] = {}
        labels: Dict[str, str] = {}

        graph["1"] = {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": UNET_FILENAME,
                "weight_dtype": req.unet_weight_dtype,
            },
        }
        labels["1"] = "加载 Qwen-Image 2.1 扩散主模型"

        graph["2"] = {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": CLIP_FILENAME,
                "type": "qwen_image",
                "device": req.clip_device,
            },
        }
        labels["2"] = "加载 Qwen3-VL 视觉文本编码器"

        graph["3"] = {
            "class_type": "VAELoader",
            "inputs": {
                "vae_name": VAE_FILENAME,
            },
        }
        labels["3"] = "加载 Qwen-Image 2.1 VAE"

        model_ref: List[Any] = ["1", 0]
        clip_ref: List[Any] = ["2", 0]

        # Chain 0..N dynamic LoRA nodes cleanly
        for idx, slot in enumerate(resolved_loras):
            nid = f"lora_{idx + 1}"
            if slot.get("apply_to_clip"):
                graph[nid] = {
                    "class_type": "LoraLoader",
                    "inputs": {
                        "model": model_ref,
                        "clip": clip_ref,
                        "lora_name": slot["filename"],
                        "strength_model": float(slot["strength_model"]),
                        "strength_clip": float(slot["strength_clip"]),
                    },
                }
                model_ref = [nid, 0]
                clip_ref = [nid, 1]
            else:
                graph[nid] = {
                    "class_type": "LoraLoaderModelOnly",
                    "inputs": {
                        "model": model_ref,
                        "lora_name": slot["filename"],
                        "strength_model": float(slot["strength_model"]),
                    },
                }
                model_ref = [nid, 0]
            labels[nid] = f"挂载 LoRA ({slot['filename']})"

        if req.auraflow_shift is not None:
            graph["shift_override"] = {
                "class_type": "ModelSamplingAuraFlow",
                "inputs": {
                    "model": model_ref,
                    "shift": float(req.auraflow_shift),
                },
            }
            model_ref = ["shift_override", 0]
            labels["shift_override"] = "应用采样时间步偏移覆写"

        graph["5"] = {
            "class_type": "QwenImage21Cache",
            "inputs": {
                "model": model_ref,
                "device": kv_device,
                "dtype": req.kv_cache_dtype,
            },
        }
        model_ref = ["5", 0]
        labels["5"] = f"配置 KV 缓存 ({kv_device}/{req.kv_cache_dtype})"

        encode_inputs: Dict[str, Any] = {
            "clip": clip_ref,
            "prompt": req.prompt,
            "negative_prompt": req.negative_prompt,
            "resolution": ref_res if staged_ref_names else max(1024, canvas_w),
        }

        has_refs = len(staged_ref_names) > 0
        for idx, staged_name in enumerate(staged_ref_names):
            load_id = f"load_ref_{idx + 1}"
            graph[load_id] = {
                "class_type": "LoadImage",
                "inputs": {"image": staged_name},
            }
            labels[load_id] = f"读取参考图 <image{idx + 1}>"
            encode_inputs[f"images.image_{idx + 1}"] = [load_id, 0]

        use_vae_ref = has_refs and req.reference_conditioning_mode == "vae_and_vision"
        if use_vae_ref:
            encode_inputs["vae"] = ["3", 0]

        graph["6"] = {
            "class_type": "TextEncodeQwenImage21",
            "inputs": encode_inputs,
        }
        labels["6"] = "Qwen3-VL 多模态指令编码"

        # Choose output latent source
        if use_vae_ref and use_ref_latent:
            latent_ref: List[Any] = ["6", 2]
            if req.batch_size > 1:
                graph["7_repeat"] = {
                    "class_type": "RepeatLatentBatch",
                    "inputs": {
                        "samples": latent_ref,
                        "amount": req.batch_size,
                    },
                }
                latent_ref = ["7_repeat", 0]
                labels["7_repeat"] = f"扩展批处理潜空间 (×{req.batch_size})"
        else:
            graph["7"] = {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": canvas_w,
                    "height": canvas_h,
                    "batch_size": req.batch_size,
                },
            }
            latent_ref = ["7", 0]
            labels["7"] = f"初始化潜空间 ({canvas_w}×{canvas_h} ×{req.batch_size})"

        graph["8"] = {
            "class_type": "KSampler",
            "inputs": {
                "model": model_ref,
                "seed": actual_seed,
                "steps": req.steps,
                "cfg": req.cfg,
                "sampler_name": req.sampler_name,
                "scheduler": req.scheduler,
                "positive": ["6", 0],
                "negative": ["6", 1],
                "latent_image": latent_ref,
                "denoise": req.denoise,
            },
        }
        labels["8"] = "扩散去噪采样"

        graph["9"] = {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["8", 0],
                "vae": ["3", 0],
            },
        }
        labels["9"] = "VAE 高清图像解码"

        save_id = "10"
        graph[save_id] = {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["9", 0],
                "filename_prefix": f"studio_qwen21/qwen21_{uuid.uuid4().hex[:8]}",
            },
        }
        labels[save_id] = "导出图像文件"
        return graph, labels, save_id

    def _run_generation(self, req: QwenImageGenerateRequest, on_progress: ProgressFn) -> QwenImageResult:
        warnings: List[str] = []
        if req.negative_prompt.strip() and req.cfg <= 1.01:
            warnings.append(
                "当前 CFG 为 1.0，反向提示词不会产生抑制作用；如需让反向提示词生效，建议将 CFG 调高至 2.5 ~ 4.0。"
            )

        refs = req.effective_references() if req.mode != "t2i" else []
        if refs and "<image1>" not in req.prompt:
            warnings.append(
                "提示词中未显式出现 <image1> 标记；在指令中使用 <image1>、<image2> 可帮助 Qwen3-VL 更精准锁定对应参考图。"
            )

        ref_paths: List[Path] = []
        ref_urls: List[str] = []
        for ref in refs:
            p = self.storage.resolve_input_ref(ref)
            ref_paths.append(p)
            if ref.startswith("preset:"):
                ref_urls.append(f"/api/v1/presets/{ref.split(':', 1)[1]}")
            elif ref.startswith("output:"):
                ref_urls.append(f"/api/v1/outputs/{ref.split(':', 1)[1]}")
            else:
                ref_urls.append(f"/api/v1/files/{ref}")

        # 1. Resolve / dynamically download enabled LoRA slots
        enabled_slots = [s for s in req.loras if s.enabled and s.lora.strip()]
        resolved_loras: List[Dict[str, Any]] = []
        if enabled_slots:
            span_per = 0.16 / len(enabled_slots)
            for idx, slot in enumerate(enabled_slots):
                p0 = 0.03 + idx * span_per
                p1 = p0 + span_per
                entry = self.lora_manager.ensure_available(
                    slot.lora,
                    token=slot.token,
                    on_progress=on_progress,
                    progress_range=(p0, p1),
                )
                resolved_loras.append(
                    {
                        "filename": entry.filename,
                        "label": entry.label,
                        "strength_model": round(slot.strength_model, 3),
                        "apply_to_clip": slot.apply_to_clip,
                        "strength_clip": round(slot.strength_clip, 3),
                    }
                )

        actual_seed = req.seed if req.seed > 0 else (secrets.randbelow(2**53 - 2) + 1)
        canvas_w, canvas_h, ref_res, use_ref_latent = self._resolve_target_dimensions(req, ref_paths)
        if req.kv_cache_device == "smart":
            kv_device = "cpu" if ref_paths else "auto"
        else:
            kv_device = req.kv_cache_device

        ext_map: Dict[ImageOutputFormat, str] = {"png": ".png", "webp": ".webp", "jpeg": ".jpg"}
        out_ext = ext_map[req.output_format]

        # 2. Mock Execution Path (for local preview & instant E2E verification)
        if self.mock_mode:
            generated_items: List[GeneratedImageItem] = []
            mock_steps = min(req.steps, 12)
            for s in range(1, mock_steps + 1):
                time.sleep(0.06)
                on_progress(
                    0.20 + 0.72 * (s / mock_steps),
                    f"[Mock] Qwen-Image 2.1 正在采样（步数 {int(s * req.steps / mock_steps)}/{req.steps}）...",
                )

            for b_idx in range(req.batch_size):
                fname, dest = self.storage.allocate_output_path(f"qwen21_{req.mode}", out_ext)
                w_used, h_used = _render_mock_canvas(
                    dest,
                    width=canvas_w,
                    height=canvas_h,
                    fmt=req.output_format,
                    quality=req.output_quality,
                    seed=actual_seed + b_idx,
                    mode=req.mode,
                    prompt=req.prompt,
                    loras=resolved_loras,
                    ref_paths=ref_paths,
                )
                generated_items.append(
                    GeneratedImageItem(
                        url=f"/api/v1/outputs/{fname}",
                        filename=fname,
                        format=req.output_format,
                        width=w_used,
                        height=h_used,
                        size_bytes=dest.stat().st_size,
                    )
                )

            first = generated_items[0]
            return QwenImageResult(
                image_url=first.url,
                filename=first.filename,
                format=first.format,
                width=first.width,
                height=first.height,
                size_bytes=first.size_bytes,
                images=generated_items,
                mode=req.mode,
                used_seed=actual_seed,
                steps=req.steps,
                cfg=req.cfg,
                sampler_name=req.sampler_name,
                scheduler=req.scheduler,
                kv_cache_device_used=kv_device,
                kv_cache_dtype=req.kv_cache_dtype,
                active_loras=resolved_loras,
                reference_urls=ref_urls,
                warnings=warnings,
                mock=True,
            )

        # 3. Real Headless ComfyUI GPU Execution Path
        on_progress(0.19, "正在向推理引擎暂存参考图像与组装算子图...")
        staged_names: List[str] = []
        staged_paths: List[Path] = []
        try:
            for idx, rpath in enumerate(ref_paths):
                sname = self.comfy.stage_input_file(rpath, prefix=f"qwen_ref{idx + 1}")
                staged_names.append(sname)
                staged_paths.append(self.comfy.input_dir / sname)

            prompt_graph, node_labels, save_node_id = self._build_comfy_graph(
                req,
                actual_seed=actual_seed,
                staged_ref_names=staged_names,
                resolved_loras=resolved_loras,
                canvas_w=canvas_w,
                canvas_h=canvas_h,
                ref_res=ref_res,
                kv_device=kv_device,
                use_ref_latent=use_ref_latent,
            )

            history_entry = self.comfy.run_prompt(
                prompt_graph,
                on_progress=on_progress,
                node_labels=node_labels,
                progress_range=(0.22, 0.94),
            )

            outputs = history_entry.get("outputs") or {}
            save_out = outputs.get(save_node_id) or {}
            raw_images = save_out.get("images") or []
            if not raw_images:
                for node_out in outputs.values():
                    if isinstance(node_out, dict) and node_out.get("images"):
                        raw_images = node_out["images"]
                        break
            if not raw_images:
                raise RuntimeError("ComfyUI 推理已完成，但未产生任何图像输出。")

            on_progress(0.96, "正在封装输出图像与写入元数据...")
            generated_items = []
            for img_meta in raw_images:
                src_png = self.comfy.resolve_output_file(img_meta)
                fname, dest = self.storage.allocate_output_path(f"qwen21_{req.mode}", out_ext)
                w_out, h_out = _convert_or_copy_image(
                    src_png,
                    dest,
                    fmt=req.output_format,
                    quality=req.output_quality,
                )
                generated_items.append(
                    GeneratedImageItem(
                        url=f"/api/v1/outputs/{fname}",
                        filename=fname,
                        format=req.output_format,
                        width=w_out,
                        height=h_out,
                        size_bytes=dest.stat().st_size,
                    )
                )

            if req.release_vram_after:
                self.release_vram()

            first = generated_items[0]
            return QwenImageResult(
                image_url=first.url,
                filename=first.filename,
                format=first.format,
                width=first.width,
                height=first.height,
                size_bytes=first.size_bytes,
                images=generated_items,
                mode=req.mode,
                used_seed=actual_seed,
                steps=req.steps,
                cfg=req.cfg,
                sampler_name=req.sampler_name,
                scheduler=req.scheduler,
                kv_cache_device_used=kv_device,
                kv_cache_dtype=req.kv_cache_dtype,
                active_loras=resolved_loras,
                reference_urls=ref_urls,
                warnings=warnings,
                mock=False,
            )
        finally:
            # Clean up staged temporary input files in ComfyUI/input
            for sp in staged_paths:
                try:
                    if sp.is_file() and not sp.is_symlink():
                        sp.unlink()
                except Exception:
                    pass

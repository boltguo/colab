"""SeedVR2 Dynamic ComfyUI Operator Graph Builder, Media Metadata Prober & Mock Upscale Renderer."""
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import struct
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid
import zlib

from ...core.comfy_client import ComfyClient
from ...core.security import ensure_safe_dir
from ...core.storage import MediaStorage
from .schemas import (
    ImageOutputFormat,
    SeedVR2GenerateRequest,
    SeedVR2Result,
    VideoOutputFormat,
    align_even,
    compute_target_dimensions,
)

ProgressFn = Callable[[float, str], None]

UNET_7B_SHARP = "seedvr2_7b_sharp_fp16.safetensors"
UNET_3B_FAST = "seedvr2_3b_fp16.safetensors"
VAE_FILENAME = "seedvr2_ema_vae_fp16.safetensors"


def _probe_image_dims_stdlib(path: Path) -> Tuple[int, int]:
    """Probe natural (width, height) from Pillow or PNG/JPEG/GIF/WebP headers."""
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as im:
            return int(im.size[0]), int(im.size[1])
    except Exception:
        pass

    try:
        with path.open("rb") as f:
            head = f.read(64)
            if len(head) >= 24 and head[:8] == b"\x89PNG\r\n\x1a\n":
                w, h = struct.unpack("!II", head[16:24])
                return int(w), int(h)
            if len(head) >= 10 and head[:6] in (b"GIF87a", b"GIF89a"):
                w, h = struct.unpack("<HH", head[6:10])
                return int(w), int(h)
            if len(head) >= 30 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
                chunk_type = head[12:16]
                if chunk_type == b"VP8X" and len(head) >= 30:
                    w = 1 + int.from_bytes(head[24:27], "little")
                    h = 1 + int.from_bytes(head[27:30], "little")
                    return w, h
                if chunk_type == b"VP8 " and len(head) >= 30:
                    w, h = struct.unpack("<HH", head[26:30])
                    return int(w & 0x3FFF), int(h & 0x3FFF)
                if chunk_type == b"VP8L" and len(head) >= 25:
                    bits = struct.unpack("<I", head[21:25])[0]
                    w = (bits & 0x3FFF) + 1
                    h = ((bits >> 14) & 0x3FFF) + 1
                    return int(w), int(h)
            if len(head) >= 4 and head[:2] == b"\xff\xd8":
                f.seek(2)
                while True:
                    b = f.read(1)
                    if not b:
                        break
                    while b == b"\xff":
                        b = f.read(1)
                    if not b:
                        break
                    marker = b[0]
                    if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                        seg = f.read(7)
                        if len(seg) == 7:
                            _, _, h, w = struct.unpack("!HBHH", seg)
                            return int(w), int(h)
                        break
                    if marker in (0xD8, 0xD9) or (0xD0 <= marker <= 0xD7):
                        continue
                    len_bytes = f.read(2)
                    if len(len_bytes) < 2:
                        break
                    seg_len = struct.unpack("!H", len_bytes)[0]
                    if seg_len < 2:
                        break
                    f.seek(seg_len - 2, os.SEEK_CUR)
    except Exception:
        pass
    return 1024, 1024


def _probe_video_meta(path: Path) -> Tuple[int, int, float, float, bool]:
    """Probe (width, height, duration_sec, fps, has_audio) via ffprobe if available."""
    ffprobe_bin = shutil.which("ffprobe")
    if ffprobe_bin and path.is_file():
        try:
            proc = subprocess.run(
                [
                    ffprobe_bin,
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type,width,height,r_frame_rate,avg_frame_rate:format=duration",
                    "-of",
                    "json",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=8,
                check=True,
            )
            payload = json.loads(proc.stdout or "{}")
            streams = payload.get("streams") or []
            fmt = payload.get("format") or {}
            width, height = 1280, 720
            fps = 24.0
            has_audio = False

            for st in streams:
                ctype = st.get("codec_type")
                if ctype == "video" and width == 1280 and height == 720:
                    if st.get("width") and st.get("height"):
                        width = int(st["width"])
                        height = int(st["height"])
                    rate_str = st.get("avg_frame_rate") or st.get("r_frame_rate") or "24/1"
                    if "/" in str(rate_str):
                        num_s, den_s = str(rate_str).split("/", 1)
                        num, den = float(num_s or 0), float(den_s or 1)
                        if den > 0 and num > 0:
                            fps = round(num / den, 3)
                elif ctype == "audio":
                    has_audio = True

            dur = float(fmt.get("duration") or 0.0)
            if dur <= 0.0:
                dur = 4.0
            return max(16, width), max(16, height), round(dur, 2), fps, has_audio
        except Exception:
            pass
    return 1280, 720, 4.0, 24.0, True


def _write_fallback_png(dest: Path, width: int, height: int, seed: int) -> None:
    w = max(64, min(1024, width))
    h = max(64, min(1024, height))
    rows = bytearray()
    cx, cy = w * 0.5, h * 0.5
    rad = min(w, h) * 0.25
    r_bias = (seed * 29) % 40
    for y in range(h):
        rows.append(0)
        ty = y / max(1, h - 1)
        br = int(228 * (1 - ty) + (192 + r_bias) * ty)
        bg = int(238 * (1 - ty) + 220 * ty)
        bb = int(252 * (1 - ty) + 248 * ty)
        dy2 = (y - cy) ** 2
        for x in range(w):
            dist = math.sqrt((x - cx) ** 2 + dy2)
            if abs(dist - rad) < 3.0 or (x % 48 == 0) or (y % 48 == 0):
                rows.extend((37, 99, 235))
            else:
                rows.extend((max(0, min(255, br)), max(0, min(255, bg)), max(0, min(255, bb))))

    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", crc)

    ihdr = struct.pack("!IIBBBBB", w, h, 8, 2, 0, 0, 0)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(rows), level=4))
        + _chunk(b"IEND", b"")
    )
    dest.write_bytes(png_bytes)


def _render_mock_upscaled_image(
    src_path: Path,
    dest: Path,
    *,
    target_w: int,
    target_h: int,
    fmt: ImageOutputFormat,
    quality: int,
    preserve_alpha: bool,
    seed: int,
) -> Tuple[int, int]:
    """Upscale and sharpen the uploaded image in --mock mode so A/B wipe preview works authentically."""
    # Cap mock preview output at 2560px max edge to keep local preview fast (<250ms)
    scale_cap = min(1.0, 2560.0 / max(target_w, target_h))
    out_w = align_even(round(target_w * scale_cap), minimum=64)
    out_h = align_even(round(target_h * scale_cap), minimum=64)

    try:
        from PIL import Image, ImageEnhance, ImageFilter  # type: ignore

        with Image.open(src_path) as im:
            has_alpha = preserve_alpha and ("A" in im.getbands()) and fmt != "jpeg"
            work = im.convert("RGBA" if has_alpha else "RGB")
            upscaled = work.resize((out_w, out_h), Image.Resampling.LANCZOS)
            if has_alpha:
                r, g, b, a = upscaled.split()
                rgb = Image.merge("RGB", (r, g, b))
                rgb = rgb.filter(ImageFilter.UnsharpMask(radius=1.6, percent=145, threshold=2))
                rgb = ImageEnhance.Contrast(rgb).enhance(1.06)
                r2, g2, b2 = rgb.split()
                upscaled = Image.merge("RGBA", (r2, g2, b2, a))
            else:
                upscaled = upscaled.filter(ImageFilter.UnsharpMask(radius=1.6, percent=145, threshold=2))
                upscaled = ImageEnhance.Contrast(upscaled).enhance(1.06)

            if fmt == "webp":
                upscaled.save(dest, format="WEBP", quality=quality, method=4)
            elif fmt == "jpeg":
                upscaled.convert("RGB").save(dest, format="JPEG", quality=quality, subsampling=0)
            else:
                upscaled.save(dest, format="PNG")
            return target_w, target_h
    except Exception:
        pass

    # Fallback via ffmpeg if Pillow cannot decode the input image
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin and src_path.is_file():
        try:
            subprocess.run(
                [
                    ffmpeg_bin,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(src_path),
                    "-vf",
                    f"scale={out_w}:{out_h}:flags=lanczos,unsharp=5:5:1.1:5:5:0.0",
                    "-frames:v",
                    "1",
                    str(dest),
                ],
                check=True,
                timeout=15,
            )
            if dest.is_file() and dest.stat().st_size > 0:
                return target_w, target_h
        except Exception:
            pass

    _write_fallback_png(dest, out_w, out_h, seed=seed)
    return target_w, target_h


def _render_mock_upscaled_video(
    src_path: Path,
    dest: Path,
    *,
    target_w: int,
    target_h: int,
    fmt: VideoOutputFormat,
    keep_audio: bool,
    trim_video: bool,
    start_time: float,
    duration: float,
    fps_override: float,
    seed: int,
) -> None:
    """Upscale and sharpen the uploaded video via ffmpeg in --mock mode (with synthetic fallback)."""
    ffmpeg_bin = shutil.which("ffmpeg")
    scale_cap = min(1.0, 1280.0 / max(target_w, target_h))
    out_w = align_even(round(target_w * scale_cap), minimum=128)
    out_h = align_even(round(target_h * scale_cap), minimum=128)

    if ffmpeg_bin:
        # 1) Try upscaling the real uploaded video first
        if src_path.is_file() and src_path.suffix.lower() in {
            ".mp4",
            ".webm",
            ".mov",
            ".mkv",
            ".avi",
            ".m4v",
        }:
            cmd: List[str] = [ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error"]
            if trim_video and start_time > 0:
                cmd.extend(["-ss", f"{start_time:.3f}"])
            cmd.extend(["-i", str(src_path)])
            if trim_video and duration > 0:
                cmd.extend(["-t", f"{min(duration, 10.0):.3f}"])
            else:
                cmd.extend(["-t", "8.0"])

            vf = f"scale={out_w}:{out_h}:flags=lanczos,unsharp=5:5:1.15:5:5:0.0"
            if fps_override > 0:
                vf += f",fps={fps_override:.2f}"
            cmd.extend(["-vf", vf])

            if fmt == "webm":
                cmd.extend(["-c:v", "libvpx-vp9", "-b:v", "1400k", "-pix_fmt", "yuv420p"])
                if keep_audio:
                    cmd.extend(["-c:a", "libopus", "-b:a", "96k"])
                else:
                    cmd.append("-an")
            else:
                cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-pix_fmt", "yuv420p"])
                if fmt == "mp4":
                    cmd.extend(["-movflags", "+faststart"])
                if keep_audio:
                    cmd.extend(["-c:a", "aac", "-b:a", "128k"])
                else:
                    cmd.append("-an")

            cmd.append(str(dest))
            try:
                subprocess.run(cmd, check=True, timeout=25)
                if dest.is_file() and dest.stat().st_size > 1024:
                    return
            except Exception:
                pass

        # 2) Fallback to synthetic test pattern video if input was a non-video stub
        freq = 240 + (seed % 90)
        syn_cmd: List[str] = [
            ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={out_w}x{out_h}:rate=24:duration=3.0",
        ]
        if keep_audio:
            syn_cmd.extend(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    f"aevalsrc='0.1*sin(2*PI*{freq}*t)|0.1*sin(2*PI*{int(freq * 1.25)}*t)':s=32000:d=3.0",
                ]
            )
        if fmt == "webm":
            syn_cmd.extend(["-c:v", "libvpx-vp9", "-b:v", "1000k", "-pix_fmt", "yuv420p"])
            if keep_audio:
                syn_cmd.extend(["-c:a", "libopus", "-b:a", "96k"])
        else:
            syn_cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-pix_fmt", "yuv420p"])
            if keep_audio:
                syn_cmd.extend(["-c:a", "aac", "-b:a", "128k"])
        syn_cmd.append(str(dest))
        try:
            subprocess.run(syn_cmd, check=True, timeout=20)
            if dest.is_file() and dest.stat().st_size > 0:
                return
        except Exception:
            pass

    dest.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom\x00\x00\x00\x08free")


def _convert_or_copy_image(
    src_png: Path,
    dest: Path,
    fmt: ImageOutputFormat,
    quality: int,
) -> Tuple[int, int]:
    """Read actual output image dimensions and optionally transcode PNG -> WebP / JPEG."""
    try:
        from PIL import Image  # type: ignore

        with Image.open(src_png) as img:
            w, h = img.size
            if fmt == "png":
                shutil.copy2(src_png, dest)
            elif fmt == "webp":
                img.save(dest, format="WEBP", quality=quality, method=4)
            else:
                img.convert("RGB").save(dest, format="JPEG", quality=quality, subsampling=0)
            return int(w), int(h)
    except Exception:
        shutil.copy2(src_png, dest)
        return _probe_image_dims_stdlib(src_png)


class SeedVR2Runner:
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

    def is_ready(self) -> Tuple[bool, bool]:
        if self.mock_mode:
            return True, True
        up = self.comfy.is_ready(timeout=2.0)
        return up, up

    def release_vram(self) -> None:
        if self.mock_mode:
            return
        self.comfy.free_memory(unload_models=True, free_memory=True)

    def execute_task(self, raw_params: Dict[str, Any], on_progress: ProgressFn) -> Dict[str, Any]:
        req = SeedVR2GenerateRequest.model_validate(raw_params)
        return self._run_upscale(req, on_progress).model_dump()

    def _ref_to_public_url(self, ref: str) -> str:
        if ref.startswith("preset:"):
            return f"/api/v1/presets/{ref.split(':', 1)[1]}"
        if ref.startswith("output:"):
            return f"/api/v1/outputs/{ref.split(':', 1)[1]}"
        return f"/api/v1/files/{ref}"

    @staticmethod
    def _build_resize_inputs(req: SeedVR2GenerateRequest, source_ref: List[Any]) -> Dict[str, Any]:
        inputs: Dict[str, Any] = {
            "input": source_ref,
            "scale_method": req.upscale_interpolation,
        }
        if req.sizing_mode == "multiplier":
            inputs["resize_type"] = "scale by multiplier"
            inputs["resize_type.multiplier"] = float(req.scale_factor)
        elif req.sizing_mode == "shorter_edge":
            inputs["resize_type"] = "scale shorter dimension"
            inputs["resize_type.shorter_size"] = int(req.target_shorter_edge)
        elif req.sizing_mode == "longer_edge":
            inputs["resize_type"] = "scale longer dimension"
            inputs["resize_type.longer_size"] = int(req.target_longer_edge)
        else:
            inputs["resize_type"] = "scale dimensions"
            inputs["resize_type.width"] = int(req.target_width)
            inputs["resize_type.height"] = int(req.target_height)
            inputs["resize_type.crop"] = req.crop_mode
        return inputs

    def _build_comfy_graph(
        self,
        req: SeedVR2GenerateRequest,
        *,
        actual_seed: int,
        staged_input_name: str,
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str], str]:
        """Dynamically assemble the SeedVR2 operator graph for Image or Video Super-Resolution."""
        graph: Dict[str, Dict[str, Any]] = {}
        labels: Dict[str, str] = {}

        unet_name = UNET_7B_SHARP if req.model_variant == "7b_sharp" else UNET_3B_FAST
        model_title = "SeedVR2 7B Sharp FP16" if req.model_variant == "7b_sharp" else "SeedVR2 3B Fast FP16"

        graph["1"] = {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": unet_name,
                "weight_dtype": req.unet_weight_dtype,
            },
        }
        labels["1"] = f"加载 {model_title} 超分主模型"

        graph["2"] = {
            "class_type": "VAELoader",
            "inputs": {"vae_name": VAE_FILENAME},
        }
        labels["2"] = "加载 SeedVR2 EMA 视频/图像 VAE"

        if req.mode == "image":
            graph["load_img"] = {
                "class_type": "LoadImage",
                "inputs": {"image": staged_input_name},
            }
            labels["load_img"] = "读取源图像"

            if req.preserve_alpha:
                graph["join_alpha"] = {
                    "class_type": "JoinImageWithAlpha",
                    "inputs": {
                        "image": ["load_img", 0],
                        "alpha": ["load_img", 1],
                    },
                }
                labels["join_alpha"] = "提取并保留 Alpha 透明通道"
                resize_src = ["join_alpha", 0]
            else:
                resize_src = ["load_img", 0]

            graph["resize"] = {
                "class_type": "ResizeImageMaskNode",
                "inputs": self._build_resize_inputs(req, resize_src),
            }
            labels["resize"] = "按目标超分尺寸预插值放大"

            graph["preproc"] = {
                "class_type": "SeedVR2Preprocess",
                "inputs": {"resized_images": ["resize", 0]},
            }
            labels["preproc"] = "SeedVR2 16px 边缘对齐预处理"

            graph["vae_enc"] = {
                "class_type": "VAEEncodeTiled",
                "inputs": {
                    "pixels": ["preproc", 0],
                    "vae": ["2", 0],
                    "tile_size": int(req.vae_tile_size),
                    "overlap": int(req.vae_tile_overlap),
                    "temporal_size": 4096,
                    "temporal_overlap": 8,
                },
            }
            labels["vae_enc"] = f"Tiled VAE 分块编码 ({req.vae_tile_size}px)"

            graph["cond"] = {
                "class_type": "SeedVR2Conditioning",
                "inputs": {
                    "model": ["1", 0],
                    "vae_conditioning": ["vae_enc", 0],
                },
            }
            labels["cond"] = "构建 SeedVR2 高频特征条件"

            graph["sample"] = {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "seed": int(actual_seed),
                    "steps": int(req.steps),
                    "cfg": float(req.cfg),
                    "sampler_name": req.sampler_name,
                    "scheduler": req.scheduler,
                    "positive": ["cond", 0],
                    "negative": ["cond", 1],
                    "latent_image": ["vae_enc", 0],
                    "denoise": float(req.denoise),
                },
            }
            labels["sample"] = f"SeedVR2 扩散纹理修复 ({req.steps} 步)"

            graph["vae_dec"] = {
                "class_type": "VAEDecodeTiled",
                "inputs": {
                    "samples": ["sample", 0],
                    "vae": ["2", 0],
                    "tile_size": int(req.vae_tile_size),
                    "overlap": int(req.vae_tile_overlap),
                    "temporal_size": 4096,
                    "temporal_overlap": 8,
                },
            }
            labels["vae_dec"] = f"Tiled VAE 分块解码 ({req.vae_tile_size}px)"

            graph["postproc"] = {
                "class_type": "SeedVR2PostProcessing",
                "inputs": {
                    "images": ["vae_dec", 0],
                    "original_resized_images": ["resize", 0],
                    "color_correction_method": req.color_correction,
                },
            }
            labels["postproc"] = f"几何裁剪与色彩校正 ({req.color_correction})"

            save_id = "save_out"
            graph[save_id] = {
                "class_type": "SaveImage",
                "inputs": {
                    "images": ["postproc", 0],
                    "filename_prefix": f"studio_seedvr2/img_{uuid.uuid4().hex[:8]}",
                },
            }
            labels[save_id] = "输出超分图像"
            return graph, labels, save_id

        # Video Super-Resolution Branch
        graph["load_vid"] = {
            "class_type": "LoadVideo",
            "inputs": {"file": staged_input_name},
        }
        labels["load_vid"] = "读取待超分视频容器"

        if req.trim_video and (req.start_time > 0.0 or req.duration > 0.0):
            graph["trim_vid"] = {
                "class_type": "Video Slice",
                "inputs": {
                    "video": ["load_vid", 0],
                    "start_time": float(req.start_time),
                    "duration": float(req.duration),
                    "strict_duration": False,
                },
            }
            labels["trim_vid"] = f"截取视频片段 (起 {req.start_time}s / 长 {req.duration or '至片尾'}s)"
            vid_ref = ["trim_vid", 0]
        else:
            vid_ref = ["load_vid", 0]

        graph["demux"] = {
            "class_type": "GetVideoComponents",
            "inputs": {"video": vid_ref},
        }
        labels["demux"] = "解复用视频帧序列、原声音轨与帧率元数据"

        graph["resize"] = {
            "class_type": "ResizeImageMaskNode",
            "inputs": self._build_resize_inputs(req, ["demux", 0]),
        }
        labels["resize"] = "视频帧序列预放大"

        graph["preproc"] = {
            "class_type": "SeedVR2Preprocess",
            "inputs": {"resized_images": ["resize", 0]},
        }
        labels["preproc"] = "SeedVR2 4n+1 时间与 16px 空间对齐"

        graph["vae_enc"] = {
            "class_type": "VAEEncodeTiled",
            "inputs": {
                "pixels": ["preproc", 0],
                "vae": ["2", 0],
                "tile_size": int(req.vae_tile_size),
                "overlap": int(req.vae_tile_overlap),
                "temporal_size": int(req.vae_temporal_size),
                "temporal_overlap": int(req.vae_temporal_overlap),
            },
        }
        labels["vae_enc"] = "时空 Tiled VAE 编码"

        if req.split_latent:
            chunk_inputs: Dict[str, Any] = {
                "latent": ["vae_enc", 0],
                "temporal_overlap": int(req.temporal_overlap),
                "chunking_mode": req.chunking_mode,
            }
            if req.chunking_mode == "manual":
                chunk_inputs["chunking_mode.frames_per_chunk"] = int(req.frames_per_chunk)
            graph["chunk"] = {
                "class_type": "SeedVR2TemporalChunk",
                "inputs": chunk_inputs,
            }
            labels["chunk"] = (
                "按剩余显存自动切分时间块"
                if req.chunking_mode == "auto"
                else f"切分时间块 (每块 {req.frames_per_chunk} 帧)"
            )
            cond_latent_ref = ["chunk", 0]
            sample_latent_ref = ["chunk", 0]
        else:
            cond_latent_ref = ["vae_enc", 0]
            sample_latent_ref = ["vae_enc", 0]

        graph["cond"] = {
            "class_type": "SeedVR2Conditioning",
            "inputs": {
                "model": ["1", 0],
                "vae_conditioning": cond_latent_ref,
            },
        }
        labels["cond"] = "构建视频时空超分条件"

        graph["sample"] = {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "seed": int(actual_seed),
                "steps": int(req.steps),
                "cfg": float(req.cfg),
                "sampler_name": req.sampler_name,
                "scheduler": req.scheduler,
                "positive": ["cond", 0],
                "negative": ["cond", 1],
                "latent_image": sample_latent_ref,
                "denoise": float(req.denoise),
            },
        }
        labels["sample"] = f"SeedVR2 视频超分采样 ({req.steps} 步)"

        if req.split_latent:
            graph["merge"] = {
                "class_type": "SeedVR2TemporalMerge",
                "inputs": {
                    "latents": ["sample", 0],
                    "temporal_overlap": ["chunk", 1],
                },
            }
            labels["merge"] = "Hann 窗平滑融合时间分块潜变量"
            decode_latent_ref = ["merge", 0]
        else:
            decode_latent_ref = ["sample", 0]

        graph["vae_dec"] = {
            "class_type": "VAEDecodeTiled",
            "inputs": {
                "samples": decode_latent_ref,
                "vae": ["2", 0],
                "tile_size": int(req.vae_tile_size),
                "overlap": int(req.vae_tile_overlap),
                "temporal_size": int(req.vae_temporal_size),
                "temporal_overlap": int(req.vae_temporal_overlap),
            },
        }
        labels["vae_dec"] = "时空 Tiled VAE 解码"

        graph["postproc"] = {
            "class_type": "SeedVR2PostProcessing",
            "inputs": {
                "images": ["vae_dec", 0],
                "original_resized_images": ["resize", 0],
                "color_correction_method": req.color_correction,
            },
        }
        labels["postproc"] = f"帧长还原与色彩对齐 ({req.color_correction})"

        create_vid_inputs: Dict[str, Any] = {
            "images": ["postproc", 0],
            "fps": float(req.fps_override) if req.fps_override > 0 else ["demux", 2],
            "bit_depth": (
                ["demux", 3]
                if req.bit_depth == "match_input"
                else (int(req.bit_depth) if req.bit_depth in ("8", "10") else "auto")
            ),
            "color_space": ["demux", 4] if req.color_space == "match_input" else req.color_space,
            "codec": "none",
        }
        if req.keep_audio:
            create_vid_inputs["audio"] = ["demux", 1]

        graph["create_vid"] = {
            "class_type": "CreateVideo",
            "inputs": create_vid_inputs,
        }
        labels["create_vid"] = "重封装超分视频流与原声轨"

        save_id = "save_out"
        save_inputs: Dict[str, Any] = {
            "video": ["create_vid", 0],
            "filename_prefix": f"studio_seedvr2/vid_{uuid.uuid4().hex[:8]}",
            "format": req.video_output_format,
        }
        if req.video_codec == "auto":
            save_inputs["format.codec"] = "auto"
        else:
            save_inputs["format.codec"] = req.video_codec
            save_inputs["format.codec.encoding"] = "re-encode"
            save_inputs["format.codec.encoding.crf"] = float(req.crf)

        graph[save_id] = {
            "class_type": "SaveVideo",
            "inputs": save_inputs,
        }
        labels[save_id] = f"导出 {req.video_output_format.upper()} 超分成片"
        return graph, labels, save_id

    def _run_upscale(self, req: SeedVR2GenerateRequest, on_progress: ProgressFn) -> SeedVR2Result:
        warnings: List[str] = []
        src_path = self.storage.resolve_input_ref(req.input_file)
        input_url = self._ref_to_public_url(req.input_file)
        actual_seed = req.seed if req.seed > 0 else (secrets.randbelow(2147483646) + 1)
        model_label = (
            "SeedVR2 7B Sharp (FP16)"
            if req.model_variant == "7b_sharp"
            else "SeedVR2 3B Fast (FP16)"
        )

        if req.mode == "image":
            in_w, in_h = _probe_image_dims_stdlib(src_path)
            in_dur: Optional[float] = None
            in_fps: Optional[float] = None
            src_has_audio = False
        else:
            in_w, in_h, probed_dur, probed_fps, src_has_audio = _probe_video_meta(src_path)
            if req.trim_video:
                rem = max(0.1, probed_dur - req.start_time)
                in_dur = round(min(rem, req.duration) if req.duration > 0 else rem, 2)
            else:
                in_dur = probed_dur
            in_fps = req.fps_override if req.fps_override > 0 else probed_fps

        out_w, out_h = compute_target_dimensions(
            in_w,
            in_h,
            sizing_mode=req.sizing_mode,
            scale_factor=req.scale_factor,
            target_shorter_edge=req.target_shorter_edge,
            target_longer_edge=req.target_longer_edge,
            target_width=req.target_width,
            target_height=req.target_height,
        )
        eff_scale = round(max(out_w / max(1, in_w), out_h / max(1, in_h)), 2)

        if req.mode == "video" and not req.split_latent and (out_w * out_h >= 2560 * 1440) and (in_dur or 0) > 6.0:
            warnings.append(
                "当前目标分辨率 ≥ 2K 且视频超过 6 秒，若在 40GB 显卡出现显存吃紧，建议开启「长视频时间分块 (Split Latent)」。"
            )

        # 1. Mock Preview Path
        if self.mock_mode:
            on_progress(0.18, f"[Mock] 正在加载 {model_label} 与 Tiled VAE...")
            mock_ticks = max(2, min(8, req.steps * 2))
            for i in range(1, mock_ticks + 1):
                time.sleep(0.07)
                on_progress(
                    0.20 + 0.62 * (i / mock_ticks),
                    f"[Mock] SeedVR2 超分细节重建中（{in_w}×{in_h} → {out_w}×{out_h}）...",
                )
            on_progress(0.88, f"[Mock] 正在执行 {req.color_correction.upper()} 色彩对齐与封装...")

            if req.mode == "image":
                ext_map_img: Dict[ImageOutputFormat, str] = {
                    "png": ".png",
                    "webp": ".webp",
                    "jpeg": ".jpg",
                }
                fname, dest = self.storage.allocate_output_path(
                    f"seedvr2_img_{req.model_variant}",
                    ext_map_img[req.image_output_format],
                )
                _render_mock_upscaled_image(
                    src_path,
                    dest,
                    target_w=out_w,
                    target_h=out_h,
                    fmt=req.image_output_format,
                    quality=req.image_quality,
                    preserve_alpha=req.preserve_alpha,
                    seed=actual_seed,
                )
                return SeedVR2Result(
                    media_type="image",
                    mode="image",
                    model_variant=req.model_variant,
                    model_label=model_label,
                    output_url=f"/api/v1/outputs/{fname}",
                    image_url=f"/api/v1/outputs/{fname}",
                    filename=fname,
                    format=req.image_output_format,
                    size_bytes=dest.stat().st_size,
                    input_url=input_url,
                    input_width=in_w,
                    input_height=in_h,
                    width=out_w,
                    height=out_h,
                    effective_scale=eff_scale,
                    duration_sec=None,
                    fps=None,
                    has_audio=False,
                    used_seed=actual_seed,
                    steps=req.steps,
                    cfg=req.cfg,
                    denoise=req.denoise,
                    color_correction=req.color_correction,
                    split_latent=False,
                    warnings=warnings,
                    mock=True,
                )

            ext_map_vid: Dict[VideoOutputFormat, str] = {
                "mp4": ".mp4",
                "webm": ".webm",
                "mkv": ".mkv",
            }
            fname, dest = self.storage.allocate_output_path(
                f"seedvr2_vid_{req.model_variant}",
                ext_map_vid[req.video_output_format],
            )
            _render_mock_upscaled_video(
                src_path,
                dest,
                target_w=out_w,
                target_h=out_h,
                fmt=req.video_output_format,
                keep_audio=req.keep_audio,
                trim_video=req.trim_video,
                start_time=req.start_time,
                duration=req.duration,
                fps_override=req.fps_override,
                seed=actual_seed,
            )
            return SeedVR2Result(
                media_type="video",
                mode="video",
                model_variant=req.model_variant,
                model_label=model_label,
                output_url=f"/api/v1/outputs/{fname}",
                video_url=f"/api/v1/outputs/{fname}",
                filename=fname,
                format=req.video_output_format,
                size_bytes=dest.stat().st_size,
                input_url=input_url,
                input_width=in_w,
                input_height=in_h,
                width=out_w,
                height=out_h,
                effective_scale=eff_scale,
                duration_sec=in_dur,
                fps=in_fps,
                has_audio=bool(req.keep_audio and src_has_audio),
                used_seed=actual_seed,
                steps=req.steps,
                cfg=req.cfg,
                denoise=req.denoise,
                color_correction=req.color_correction,
                split_latent=req.split_latent,
                warnings=warnings,
                mock=True,
            )

        # 2. Real Headless ComfyUI GPU Execution Path
        on_progress(0.14, f"正在暂存源素材并动态构建 {model_label} 算子图...")
        staged_name = self.comfy.stage_input_file(src_path, prefix=f"seedvr2_{req.mode}")
        staged_full_path = self.comfy.input_dir / staged_name

        try:
            prompt_graph, node_labels, save_node_id = self._build_comfy_graph(
                req,
                actual_seed=actual_seed,
                staged_input_name=staged_name,
            )

            history_entry = self.comfy.run_prompt(
                prompt_graph,
                on_progress=on_progress,
                node_labels=node_labels,
                progress_range=(0.16, 0.94),
                timeout_sec=3600.0,
            )

            outputs = history_entry.get("outputs") or {}
            save_out = outputs.get(save_node_id) or {}
            raw_items = (
                save_out.get("images")
                or save_out.get("videos")
                or save_out.get("gifs")
                or []
            )
            if not raw_items:
                for node_out in outputs.values():
                    if isinstance(node_out, dict):
                        cand = node_out.get("images") or node_out.get("videos") or node_out.get("gifs")
                        if cand:
                            raw_items = cand
                            break
            if not raw_items:
                raise RuntimeError("SeedVR2 推理已完成，但未产生任何输出文件。")

            on_progress(0.96, "正在导出超分结果并写入输出仓库...")
            comfy_out_path = self.comfy.resolve_output_file(raw_items[0])

            if req.mode == "image":
                ext_map_img = {"png": ".png", "webp": ".webp", "jpeg": ".jpg"}
                fname, dest = self.storage.allocate_output_path(
                    f"seedvr2_img_{req.model_variant}",
                    ext_map_img[req.image_output_format],
                )
                actual_w, actual_h = _convert_or_copy_image(
                    comfy_out_path,
                    dest,
                    req.image_output_format,
                    req.image_quality,
                )
                if req.release_vram_after:
                    self.release_vram()
                return SeedVR2Result(
                    media_type="image",
                    mode="image",
                    model_variant=req.model_variant,
                    model_label=model_label,
                    output_url=f"/api/v1/outputs/{fname}",
                    image_url=f"/api/v1/outputs/{fname}",
                    filename=fname,
                    format=req.image_output_format,
                    size_bytes=dest.stat().st_size,
                    input_url=input_url,
                    input_width=in_w,
                    input_height=in_h,
                    width=actual_w,
                    height=actual_h,
                    effective_scale=round(max(actual_w / max(1, in_w), actual_h / max(1, in_h)), 2),
                    duration_sec=None,
                    fps=None,
                    has_audio=False,
                    used_seed=actual_seed,
                    steps=req.steps,
                    cfg=req.cfg,
                    denoise=req.denoise,
                    color_correction=req.color_correction,
                    split_latent=False,
                    warnings=warnings,
                    mock=False,
                )

            ext_map_vid = {"mp4": ".mp4", "webm": ".webm", "mkv": ".mkv"}
            actual_ext = comfy_out_path.suffix.lower() or ext_map_vid[req.video_output_format]
            fname, dest = self.storage.copy_to_output(
                comfy_out_path,
                f"seedvr2_vid_{req.model_variant}",
                actual_ext,
            )
            vid_w, vid_h, vid_dur, vid_fps, vid_aud = _probe_video_meta(dest)
            if req.release_vram_after:
                self.release_vram()

            return SeedVR2Result(
                media_type="video",
                mode="video",
                model_variant=req.model_variant,
                model_label=model_label,
                output_url=f"/api/v1/outputs/{fname}",
                video_url=f"/api/v1/outputs/{fname}",
                filename=fname,
                format=req.video_output_format,
                size_bytes=dest.stat().st_size,
                input_url=input_url,
                input_width=in_w,
                input_height=in_h,
                width=vid_w or out_w,
                height=vid_h or out_h,
                effective_scale=round(max((vid_w or out_w) / max(1, in_w), (vid_h or out_h) / max(1, in_h)), 2),
                duration_sec=vid_dur or in_dur,
                fps=vid_fps or in_fps,
                has_audio=vid_aud,
                used_seed=actual_seed,
                steps=req.steps,
                cfg=req.cfg,
                denoise=req.denoise,
                color_correction=req.color_correction,
                split_latent=req.split_latent,
                warnings=warnings,
                mock=False,
            )
        finally:
            try:
                if staged_full_path.is_file() and not staged_full_path.is_symlink():
                    staged_full_path.unlink()
            except Exception:
                pass

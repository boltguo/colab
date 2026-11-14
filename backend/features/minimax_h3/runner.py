"""MiniMax-H3 Dynamic ComfyUI Graph Builder, Multimodal Reference Stager & Mock AV Renderer."""
import hashlib
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

from ...core.comfy_client import ComfyClient
from ...core.lora_manager import CuratedLoraSpec, LoraDownloadRequest, LoraManager
from ...core.security import ensure_safe_dir, ensure_safe_path
from ...core.storage import MediaStorage
from .schemas import (
    MiniMaxH3GenerateRequest,
    MiniMaxH3Result,
    NATIVE_FPS,
    VideoOutputFormat,
    compute_h3_dimensions,
    compute_matched_dimensions,
    snap32,
)

ProgressFn = Callable[[float, str], None]


def _prepare_reference_video(src: Path, dest: Path, *, duration_sec: float, include_audio: bool) -> None:
    """Keep reference motion and soundtrack on the H3 node's native 24 fps timeline."""
    ensure_safe_path(src)
    ensure_safe_dir(dest.parent)
    ensure_safe_path(dest, stop_at=dest.parent)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("参考视频预处理需要 FFmpeg，请先在运行环境安装 ffmpeg。")
    command = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src), "-t", f"{duration_sec:.8f}", "-map", "0:v:0",
        "-vf", "fps=24,scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
    ]
    if include_audio:
        command.extend(["-map", "0:a:0", "-c:a", "aac", "-b:a", "192k"])
    else:
        command.append("-an")
    command.append(str(dest))
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("参考视频预处理超时，请换用较短的视频片段。") from exc
    if result.returncode:
        if include_audio and "matches no streams" in result.stderr:
            raise ValueError("参考视频没有音轨，请关闭该视频的「提取视频原声」后重试。")
        raise RuntimeError("参考视频无法读取或转换，请换用可播放的 MP4 / MOV / WebM 文件。")


FL2VA_UNET_FILENAME = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
REF2VA_UNET_FILENAME = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
CLIP_FILENAME = "qwen3vl_32b_minimax_h3_int8_convrot.safetensors"
VIDEO_VAE_FILENAME = "minimax_h3_video_vae_int8_convrot.safetensors"
AUDIO_VAE_FILENAME = "minimax_h3_audio_vae_fp32.safetensors"

FL2V_TURBO_LORA = "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
REF2V_TURBO_LORA = "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"

CURATED_H3_LORAS: List[CuratedLoraSpec] = [
    CuratedLoraSpec(
        id="fl2v_turbo_8step",
        filename=FL2V_TURBO_LORA,
        label="官方 FL2V 8 步极速 Turbo (文生视频 / 首尾帧专用)",
        description="MiniMax-H3 FL2VA 蒸馏加速权重（8 步即可完成音画同生采样，开启上方「Turbo 极速加速」时会自动挂载，无需在此重复勾选）。",
        repo_id="lightx2v/Minimax-h3-Turbo",
        revision="30f485ed874aa44c8183348ad361c5eabad318da",
        repo_filename=FL2V_TURBO_LORA,
        expected_size=1956193000,
        recommended_strength=1.0,
        trigger_words=(),
        tags=("官方内置", "8步加速", "文生/首尾帧"),
    ),
    CuratedLoraSpec(
        id="ref2v_turbo_4step",
        filename=REF2V_TURBO_LORA,
        label="官方 Ref2V 4 步极速 Turbo (多模态参考专用)",
        description="MiniMax-H3 Ref2VA 蒸馏加速权重（4 步极速生成多参考视频，开启上方「Turbo 极速加速」时会自动挂载）。",
        repo_id="Comfy-Org/MiniMax-H3",
        revision="e5eb578a89295337b8ff433a035929ce0279e0b6",
        repo_filename=f"loras/{REF2V_TURBO_LORA}",
        expected_size=1956193000,
        recommended_strength=1.0,
        trigger_words=(),
        tags=("官方内置", "4步加速", "多参考R2V"),
    ),
]


def _probe_image_dims_stdlib(path: Path) -> Tuple[int, int]:
    """Probe natural (width, height) from PNG, JPEG, GIF, or WebP headers without external libs."""
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
    return 1344, 768


def _render_mock_video(
    dest: Path,
    *,
    width: int,
    height: int,
    duration_sec: float,
    fps: float,
    fmt: VideoOutputFormat,
    has_audio: bool,
    seed: int,
    mode: str,
) -> None:
    """Generate a real playable animated mock video (+ synced stereo chime audio) for local preview."""
    ffmpeg_bin = shutil.which("ffmpeg")
    # Keep mock preview encode fast (< 0.6s) while preserving exact aspect ratio
    scale = min(1.0, 960.0 / max(width, height))
    out_w = max(128, int(round((width * scale) / 2.0) * 2))
    out_h = max(128, int(round((height * scale) / 2.0) * 2))
    clip_dur = max(1.0, min(6.0, float(duration_sec)))
    out_fps = max(12, min(60, int(round(fps))))

    palette_hex = hashlib.sha256(f"{seed}:{mode}".encode("utf-8")).hexdigest()[:6]
    freq_a = 220 + (seed % 110)
    freq_b = int(freq_a * 1.25)

    if ffmpeg_bin:
        cmd: List[str] = [
            ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={out_w}x{out_h}:rate={out_fps}:duration={clip_dur:.2f}",
        ]
        if has_audio:
            cmd.extend(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    (
                        f"aevalsrc='0.12*sin(2*PI*{freq_a}*t)+0.08*sin(2*PI*{freq_b}*t)"
                        f"|0.12*sin(2*PI*{freq_a}*t)+0.08*sin(2*PI*{freq_b}*1.5*t)'"
                        f":s=32000:d={clip_dur:.2f}"
                    ),
                ]
            )

        if fmt == "webm":
            cmd.extend(["-c:v", "libvpx-vp9", "-b:v", "900k", "-pix_fmt", "yuv420p"])
            if has_audio:
                cmd.extend(["-c:a", "libopus", "-b:a", "96k"])
        else:
            cmd.extend(
                [
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-crf",
                    "23",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                ]
            )
            if has_audio:
                cmd.extend(["-c:a", "aac", "-b:a", "128k"])

        cmd.extend(["-metadata", f"title=MiniMax-H3 Mock ({mode} #{palette_hex})", str(dest)])
        try:
            subprocess.run(cmd, check=True, timeout=20)
            if dest.is_file() and dest.stat().st_size > 0:
                return
        except Exception:
            pass

    # Minimal fallback binary payload if ffmpeg is absent in a bare test runner
    dest.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom\x00\x00\x00\x08free")


class MiniMaxH3Runner:
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
            curated=CURATED_H3_LORAS,
            mock_mode=mock_mode,
        )

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

        req = MiniMaxH3GenerateRequest.model_validate(raw_params)
        return self._run_generation(req, on_progress).model_dump()

    def _ref_to_public_url(self, ref: str) -> str:
        if ref.startswith("preset:"):
            return f"/api/v1/presets/{ref.split(':', 1)[1]}"
        if ref.startswith("output:"):
            return f"/api/v1/outputs/{ref.split(':', 1)[1]}"
        return f"/api/v1/files/{ref}"

    def _resolve_target_canvas(
        self,
        req: MiniMaxH3GenerateRequest,
        anchor_image_path: Optional[Path],
    ) -> Tuple[int, int]:
        if req.aspect_ratio == "custom" or req.resolution_tier == "custom":
            return snap32(req.width), snap32(req.height)
        if req.mode != "t2v" and req.aspect_ratio == "match_input" and anchor_image_path is not None:
            rw, rh = _probe_image_dims_stdlib(anchor_image_path)
            return compute_matched_dimensions(req.resolution_tier, rw, rh)
        effective_ar = "16:9" if req.aspect_ratio == "match_input" else req.aspect_ratio
        return compute_h3_dimensions(req.resolution_tier, effective_ar)

    def _build_comfy_graph(
        self,
        req: MiniMaxH3GenerateRequest,
        *,
        actual_seed: int,
        canvas_w: int,
        canvas_h: int,
        aligned_frames: int,
        turbo_lora_filename: Optional[str],
        resolved_loras: List[Dict[str, Any]],
        staged_first_frame: Optional[str],
        staged_last_frame: Optional[str],
        staged_guide_image: Optional[str],
        staged_guide_audio: Optional[str],
        staged_ref_images: List[str],
        staged_ref_videos: List[Tuple[str, bool]],
        staged_ref_audios: List[str],
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str], str]:
        """Dynamically construct the headless ComfyUI operator graph for MiniMax-H3."""
        graph: Dict[str, Dict[str, Any]] = {}
        labels: Dict[str, str] = {}

        is_r2v = req.mode == "r2v"
        unet_name = REF2VA_UNET_FILENAME if is_r2v else FL2VA_UNET_FILENAME

        graph["1"] = {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": unet_name,
                "weight_dtype": req.unet_weight_dtype,
            },
        }
        labels["1"] = f"加载 MiniMax-H3 {'Ref2VA' if is_r2v else 'FL2VA'} 主模型"

        graph["2"] = {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": CLIP_FILENAME,
                "type": "minimax",
                "device": req.clip_device,
            },
        }
        labels["2"] = "加载 Qwen3-VL-32B 多模态文本编码器"

        graph["3"] = {
            "class_type": "VAELoader",
            "inputs": {"vae_name": VIDEO_VAE_FILENAME},
        }
        labels["3"] = "加载视频 VAE 解码器"

        graph["4"] = {
            "class_type": "VAELoader",
            "inputs": {"vae_name": AUDIO_VAE_FILENAME},
        }
        labels["4"] = "加载立体声音频 VAE 解码器"

        model_ref: List[Any] = ["1", 0]
        clip_ref: List[Any] = ["2", 0]

        # 1. Official Turbo LoRA branch
        if turbo_lora_filename:
            graph["lora_turbo"] = {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": model_ref,
                    "lora_name": turbo_lora_filename,
                    "strength_model": float(req.turbo_strength),
                },
            }
            model_ref = ["lora_turbo", 0]
            labels["lora_turbo"] = f"挂载官方 Turbo 加速 ({turbo_lora_filename})"

        # 2. Additional Custom LoRAs
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
            labels[nid] = f"挂载自定义 LoRA ({slot['filename']})"

        # 3. Optional AV Sigma Shift override
        if req.enable_sigma_shift:
            graph["sigma_shift"] = {
                "class_type": "MiniMaxH3SigmaShift",
                "inputs": {
                    "model": model_ref,
                    "shift_video": float(req.shift_video),
                    "shift_audio": float(req.shift_audio),
                },
            }
            model_ref = ["sigma_shift", 0]
            labels["sigma_shift"] = f"配置音画流偏移 (V={req.shift_video} / A={req.shift_audio})"

        use_cfg = req.cfg > 1.001

        # 4. Conditioning & Joint AV Latent Construction
        if not is_r2v:
            cond_inputs: Dict[str, Any] = {
                "clip": clip_ref,
                "vae": ["3", 0],
                "prompt": req.prompt,
                "width": canvas_w,
                "height": canvas_h,
                "length": aligned_frames,
            }
            if staged_first_frame:
                graph["load_first"] = {
                    "class_type": "LoadImage",
                    "inputs": {"image": staged_first_frame},
                }
                labels["load_first"] = "加载首帧关键帧图像"
                cond_inputs["first_frame"] = ["load_first", 0]

            if staged_last_frame:
                graph["load_last"] = {
                    "class_type": "LoadImage",
                    "inputs": {"image": staged_last_frame},
                }
                labels["load_last"] = "加载尾帧关键帧图像"
                cond_inputs["last_frame"] = ["load_last", 0]

            graph["cond_pos"] = {
                "class_type": "MiniMaxH3ImageToVideo",
                "inputs": cond_inputs,
            }
            labels["cond_pos"] = "编码音画生成条件与潜空间"
            pos_ref: List[Any] = ["cond_pos", 0]
            latent_ref: List[Any] = ["cond_pos", 1]

            neg_ref: Optional[List[Any]] = None
            if use_cfg:
                neg_inputs = dict(cond_inputs)
                neg_inputs["prompt"] = req.negative_prompt or ""
                graph["cond_neg"] = {
                    "class_type": "MiniMaxH3ImageToVideo",
                    "inputs": neg_inputs,
                }
                labels["cond_neg"] = "编码反向引导条件"
                neg_ref = ["cond_neg", 0]

            if staged_guide_image or staged_guide_audio:
                guide_inputs: Dict[str, Any] = {
                    "positive": pos_ref,
                    "latent": latent_ref,
                    "frame_idx": int(req.guide_frame_idx),
                }
                if staged_guide_image:
                    graph["load_guide_img"] = {
                        "class_type": "LoadImage",
                        "inputs": {"image": staged_guide_image},
                    }
                    labels["load_guide_img"] = "加载锚定关键帧图像"
                    guide_inputs["vae"] = ["3", 0]
                    guide_inputs["image"] = ["load_guide_img", 0]
                if staged_guide_audio:
                    graph["load_guide_aud"] = {
                        "class_type": "LoadAudio",
                        "inputs": {"audio": staged_guide_audio},
                    }
                    labels["load_guide_aud"] = "加载外部驱动音轨"
                    guide_inputs["audio_vae"] = ["4", 0]
                    guide_inputs["audio"] = ["load_guide_aud", 0]

                graph["add_guide_pos"] = {
                    "class_type": "MiniMaxH3AddGuide",
                    "inputs": guide_inputs,
                }
                labels["add_guide_pos"] = f"锚定第 {req.guide_frame_idx} 帧音画引导"
                pos_ref = ["add_guide_pos", 0]

                if use_cfg and neg_ref is not None:
                    neg_guide_inputs = dict(guide_inputs)
                    neg_guide_inputs["positive"] = neg_ref
                    graph["add_guide_neg"] = {
                        "class_type": "MiniMaxH3AddGuide",
                        "inputs": neg_guide_inputs,
                    }
                    neg_ref = ["add_guide_neg", 0]
        else:
            r2v_inputs: Dict[str, Any] = {
                "clip": clip_ref,
                "prompt": req.prompt,
                "width": canvas_w,
                "height": canvas_h,
                "length": aligned_frames,
                "ref_image_size": req.ref_image_size,
            }
            if req.ref_conditioning_mode == "vae_and_vision":
                r2v_inputs["vae"] = ["3", 0]
                r2v_inputs["audio_vae"] = ["4", 0]

            for idx, img_name in enumerate(staged_ref_images):
                nid = f"load_ref_img_{idx}"
                graph[nid] = {
                    "class_type": "LoadImage",
                    "inputs": {"image": img_name},
                }
                labels[nid] = f"加载参考图 <Picture {idx + 1}>"
                r2v_inputs[f"ref_images.ref_image_{idx}"] = [nid, 0]

            for idx, (vid_name, use_vid_audio) in enumerate(staged_ref_videos):
                load_nid = f"load_ref_vid_{idx}"
                split_nid = f"split_ref_vid_{idx}"
                graph[load_nid] = {
                    "class_type": "LoadVideo",
                    "inputs": {"file": vid_name},
                }
                graph[split_nid] = {
                    "class_type": "GetVideoComponents",
                    "inputs": {"video": [load_nid, 0]},
                }
                labels[load_nid] = f"加载参考视频 <Video {idx + 1}>"
                labels[split_nid] = f"解复用参考视频 #{idx + 1} 帧与原声"
                r2v_inputs[f"ref_videos.ref_video_{idx}"] = [split_nid, 0]
                if use_vid_audio:
                    r2v_inputs[f"ref_video_audios.ref_video_audio_{idx}"] = [split_nid, 1]

            for idx, aud_name in enumerate(staged_ref_audios):
                nid = f"load_ref_aud_{idx}"
                graph[nid] = {
                    "class_type": "LoadAudio",
                    "inputs": {"audio": aud_name},
                }
                labels[nid] = f"加载独立参考音频 #{idx + 1}"
                r2v_inputs[f"ref_audios.ref_audio_{idx}"] = [nid, 0]

            graph["cond_pos"] = {
                "class_type": "MiniMaxH3ReferenceToVideo",
                "inputs": r2v_inputs,
            }
            labels["cond_pos"] = "编码多模态参考条件 (<Picture>/<Video>/<Audio>)"
            pos_ref = ["cond_pos", 0]
            latent_ref = ["cond_pos", 1]

            neg_ref = None
            if use_cfg:
                neg_r2v_inputs = dict(r2v_inputs)
                neg_r2v_inputs["prompt"] = req.negative_prompt or ""
                graph["cond_neg"] = {
                    "class_type": "MiniMaxH3ReferenceToVideo",
                    "inputs": neg_r2v_inputs,
                }
                labels["cond_neg"] = "编码多模态反向引导条件"
                neg_ref = ["cond_neg", 0]

        # 5. Guider + SamplerCustomAdvanced
        if use_cfg and neg_ref is not None:
            graph["guider"] = {
                "class_type": "CFGGuider",
                "inputs": {
                    "model": model_ref,
                    "positive": pos_ref,
                    "negative": neg_ref,
                    "cfg": float(req.cfg),
                },
            }
            labels["guider"] = f"CFG 双路引导 (CFG={req.cfg})"
        else:
            graph["guider"] = {
                "class_type": "BasicGuider",
                "inputs": {
                    "model": model_ref,
                    "conditioning": pos_ref,
                },
            }
            labels["guider"] = "高速单路条件引导"

        graph["noise"] = {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": actual_seed},
        }
        graph["sampler_sel"] = {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": req.sampler_name},
        }
        graph["sched"] = {
            "class_type": "BasicScheduler",
            "inputs": {
                "model": model_ref,
                "scheduler": req.scheduler,
                "steps": int(req.steps),
                "denoise": float(req.denoise),
            },
        }
        labels["sched"] = f"计算采样调度 ({req.steps} 步 / {req.scheduler})"

        graph["sample"] = {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["noise", 0],
                "guider": ["guider", 0],
                "sampler": ["sampler_sel", 0],
                "sigmas": ["sched", 0],
                "latent_image": latent_ref,
            },
        }
        labels["sample"] = "音视频同步联合扩散采样"

        # 6. Video + Audio VAE Decode & Container Mux
        graph["dec_video"] = {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["sample", 0],
                "vae": ["3", 0],
            },
        }
        labels["dec_video"] = "解码视频画面序列"

        create_vid_inputs: Dict[str, Any] = {
            "images": ["dec_video", 0],
            "fps": float(req.fps),
            "bit_depth": int(req.bit_depth) if req.bit_depth in ("8", "10") else "auto",
            "color_space": req.color_space,
            "codec": "none",
        }
        if req.soundtrack_enabled:
            graph["dec_audio"] = {
                "class_type": "VAEDecodeAudio",
                "inputs": {
                    "samples": ["sample", 0],
                    "vae": ["4", 0],
                },
            }
            labels["dec_audio"] = "解码同步立体声音轨"
            create_vid_inputs["audio"] = ["dec_audio", 0]

        graph["create_vid"] = {
            "class_type": "CreateVideo",
            "inputs": create_vid_inputs,
        }
        labels["create_vid"] = "合成音画同步视频流"

        save_id = "save_vid"
        save_inputs: Dict[str, Any] = {
            "video": ["create_vid", 0],
            "filename_prefix": f"studio_h3/h3_{uuid.uuid4().hex[:8]}",
            "format": req.output_format,
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
        labels[save_id] = f"封装导出 {req.output_format.upper()} 视频文件"

        return graph, labels, save_id

    def _run_generation(self, req: MiniMaxH3GenerateRequest, on_progress: ProgressFn) -> MiniMaxH3Result:
        warnings: List[str] = []
        if req.negative_prompt.strip() and req.cfg <= 1.001:
            warnings.append(
                "当前 CFG 为 1.0，反向提示词不会产生抑制作用；如需让反向提示词生效，请将 CFG 调高至 2.0 ~ 4.0。"
            )

        is_r2v = req.mode == "r2v"
        model_variant = "Ref2VA (INT8 ConvRot)" if is_r2v else "FL2VA (INT8 ConvRot)"

        # Resolve input file paths
        first_frame_path = self.storage.resolve_input_ref(req.first_frame) if req.first_frame else None
        last_frame_path = self.storage.resolve_input_ref(req.last_frame) if req.last_frame else None
        guide_img_path = self.storage.resolve_input_ref(req.guide_image) if req.guide_image else None
        guide_aud_path = self.storage.resolve_input_ref(req.guide_audio) if req.guide_audio else None

        ref_img_refs = req.effective_ref_images() if is_r2v else []
        ref_vid_slots = req.effective_ref_videos() if is_r2v else []
        ref_aud_refs = req.effective_ref_audios() if is_r2v else []

        ref_img_paths = [self.storage.resolve_input_ref(r) for r in ref_img_refs]
        ref_vid_paths = [(self.storage.resolve_input_ref(v.file_id), v.use_video_audio) for v in ref_vid_slots]
        ref_aud_paths = [self.storage.resolve_input_ref(a) for a in ref_aud_refs]

        if is_r2v and ref_img_refs and "<Picture 1>" not in req.prompt:
            warnings.append(
                "提示词中未显式出现 <Picture 1> 标签；在提示词中使用 <Picture 1>、<Video 1>、<Audio 1> 可更精准绑定各参考素材。"
            )

        anchor_img: Optional[Path] = None
        primary_ref_image_url: Optional[str] = None
        if req.mode in ("fl2v", "i2v"):
            anchor_img = first_frame_path or last_frame_path
            if req.first_frame:
                primary_ref_image_url = self._ref_to_public_url(req.first_frame)
            elif req.last_frame:
                primary_ref_image_url = self._ref_to_public_url(req.last_frame)
        elif is_r2v and ref_img_refs:
            anchor_img = ref_img_paths[0]
            primary_ref_image_url = self._ref_to_public_url(ref_img_refs[0])

        canvas_w, canvas_h = self._resolve_target_canvas(req, anchor_img)
        aligned_frames = req.resolved_frame_count()
        actual_duration_sec = round(aligned_frames / float(req.fps), 2)
        actual_seed = req.seed if req.seed > 0 else (secrets.randbelow(2**53 - 2) + 1)

        # Ensure official Turbo LoRA + custom LoRA stack are available
        active_loras: List[Dict[str, object]] = []
        turbo_lora_filename: Optional[str] = None
        if req.turbo_enabled:
            curated_id = "ref2v_turbo_4step" if is_r2v else "fl2v_turbo_8step"
            turbo_entry = self.lora_manager.ensure_available(
                curated_id,
                on_progress=on_progress,
                progress_range=(0.02, 0.08),
            )
            turbo_lora_filename = turbo_entry.filename
            active_loras.append(
                {
                    "filename": turbo_entry.filename,
                    "label": turbo_entry.label,
                    "strength_model": round(req.turbo_strength, 3),
                    "turbo": True,
                }
            )

        enabled_slots = [s for s in req.loras if s.enabled and s.lora.strip()]
        resolved_loras: List[Dict[str, Any]] = []
        if enabled_slots:
            span_per = 0.10 / len(enabled_slots)
            for idx, slot in enumerate(enabled_slots):
                p0 = 0.08 + idx * span_per
                p1 = p0 + span_per
                entry = self.lora_manager.ensure_available(
                    slot.lora,
                    token=slot.token,
                    on_progress=on_progress,
                    progress_range=(p0, p1),
                )
                item = {
                    "filename": entry.filename,
                    "label": entry.label,
                    "strength_model": round(slot.strength_model, 3),
                    "apply_to_clip": slot.apply_to_clip,
                    "strength_clip": round(slot.strength_clip, 3),
                }
                resolved_loras.append(item)
                active_loras.append(item)

        ref_summary: Dict[str, object] = {
            "first_frame": bool(first_frame_path),
            "last_frame": bool(last_frame_path),
            "guide_audio": bool(guide_aud_path),
            "guide_image": bool(guide_img_path),
            "ref_images": len(ref_img_paths),
            "ref_videos": len(ref_vid_paths),
            "ref_audios": len(ref_aud_paths),
        }

        ext_map: Dict[VideoOutputFormat, str] = {"mp4": ".mp4", "webm": ".webm", "mkv": ".mkv"}
        out_ext = ext_map[req.output_format]

        # 1. Mock Preview Path
        if self.mock_mode:
            mock_steps = min(req.steps, 10)
            for s in range(1, mock_steps + 1):
                time.sleep(0.06)
                on_progress(
                    0.18 + 0.68 * (s / mock_steps),
                    f"[Mock] MiniMax-H3 音画同步扩散采样（步数 {int(round(s * req.steps / mock_steps))}/{req.steps}）...",
                )
            on_progress(0.90, "[Mock] 正在解码视频画面与立体声音轨并封装容器...")
            fname, dest = self.storage.allocate_output_path(f"h3_{req.mode}", out_ext)
            _render_mock_video(
                dest,
                width=canvas_w,
                height=canvas_h,
                duration_sec=actual_duration_sec,
                fps=req.fps,
                fmt=req.output_format,
                has_audio=req.soundtrack_enabled,
                seed=actual_seed,
                mode=req.mode,
            )
            return MiniMaxH3Result(
                video_url=f"/api/v1/outputs/{fname}",
                filename=fname,
                format=req.output_format,
                video_codec=req.video_codec,
                width=canvas_w,
                height=canvas_h,
                frame_count=aligned_frames,
                duration_sec=actual_duration_sec,
                fps=req.fps,
                has_audio=req.soundtrack_enabled,
                size_bytes=dest.stat().st_size,
                mode=req.mode,
                model_variant=model_variant,
                turbo_enabled=req.turbo_enabled,
                used_seed=actual_seed,
                steps=req.steps,
                cfg=req.cfg,
                sampler_name=req.sampler_name,
                scheduler=req.scheduler,
                active_loras=active_loras,
                reference_summary=ref_summary,
                primary_ref_image_url=primary_ref_image_url,
                warnings=warnings,
                mock=True,
            )

        # 2. Real Headless ComfyUI GPU Execution Path
        on_progress(0.18, "正在暂存输入素材并动态组装 MiniMax-H3 算子图...")
        staged_paths: List[Path] = []

        def _stage(src: Optional[Path], prefix: str) -> Optional[str]:
            if src is None:
                return None
            sname = self.comfy.stage_input_file(src, prefix=prefix)
            staged_paths.append(self.comfy.input_dir / sname)
            return sname

        try:
            s_first = _stage(first_frame_path, "h3_first")
            s_last = _stage(last_frame_path, "h3_last")
            s_g_img = _stage(guide_img_path, "h3_guide_img")
            s_g_aud = _stage(guide_aud_path, "h3_guide_aud")

            s_ref_imgs = [_stage(p, f"h3_pic{i + 1}") or "" for i, p in enumerate(ref_img_paths)]
            s_ref_vids = []
            for i, (path, use_audio) in enumerate(ref_vid_paths):
                staged_name = f"h3_vid{i + 1}_{uuid.uuid4().hex[:12]}.mp4"
                staged_path = self.comfy.input_dir / staged_name
                staged_paths.append(staged_path)
                on_progress(0.19, f"正在将参考视频 {i + 1} 对齐至 24 fps...")
                _prepare_reference_video(
                    path, staged_path,
                    duration_sec=aligned_frames / NATIVE_FPS,
                    include_audio=use_audio,
                )
                s_ref_vids.append((staged_name, use_audio))
            s_ref_auds = [_stage(p, f"h3_aud{i + 1}") or "" for i, p in enumerate(ref_aud_paths)]

            prompt_graph, node_labels, save_node_id = self._build_comfy_graph(
                req,
                actual_seed=actual_seed,
                canvas_w=canvas_w,
                canvas_h=canvas_h,
                aligned_frames=aligned_frames,
                turbo_lora_filename=turbo_lora_filename,
                resolved_loras=resolved_loras,
                staged_first_frame=s_first,
                staged_last_frame=s_last,
                staged_guide_image=s_g_img,
                staged_guide_audio=s_g_aud,
                staged_ref_images=s_ref_imgs,
                staged_ref_videos=s_ref_vids,
                staged_ref_audios=s_ref_auds,
            )

            history_entry = self.comfy.run_prompt(
                prompt_graph,
                on_progress=on_progress,
                node_labels=node_labels,
                progress_range=(0.20, 0.94),
                timeout_sec=3600.0,
            )

            outputs = history_entry.get("outputs") or {}
            save_out = outputs.get(save_node_id) or {}
            # SaveVideo returns ui.PreviewVideo -> {"images": [SavedResult(...)], "animated": [True]}
            raw_videos = (
                save_out.get("images")
                or save_out.get("videos")
                or save_out.get("gifs")
                or []
            )
            if not raw_videos:
                for node_out in outputs.values():
                    if isinstance(node_out, dict):
                        cand = node_out.get("images") or node_out.get("videos") or node_out.get("gifs")
                        if cand:
                            raw_videos = cand
                            break
            if not raw_videos:
                raise RuntimeError("ComfyUI 推理已完成，但未产生任何视频输出文件。")

            on_progress(0.96, "正在回收成片文件并写入输出仓库...")
            src_video = self.comfy.resolve_output_file(raw_videos[0])
            actual_ext = src_video.suffix.lower() or out_ext
            fname, dest = self.storage.copy_to_output(src_video, f"h3_{req.mode}", actual_ext)

            if req.release_vram_after:
                self.release_vram()

            return MiniMaxH3Result(
                video_url=f"/api/v1/outputs/{fname}",
                filename=fname,
                format=req.output_format,
                video_codec=req.video_codec,
                width=canvas_w,
                height=canvas_h,
                frame_count=aligned_frames,
                duration_sec=actual_duration_sec,
                fps=req.fps,
                has_audio=req.soundtrack_enabled,
                size_bytes=dest.stat().st_size,
                mode=req.mode,
                model_variant=model_variant,
                turbo_enabled=req.turbo_enabled,
                used_seed=actual_seed,
                steps=req.steps,
                cfg=req.cfg,
                sampler_name=req.sampler_name,
                scheduler=req.scheduler,
                active_loras=active_loras,
                reference_summary=ref_summary,
                primary_ref_image_url=primary_ref_image_url,
                warnings=warnings,
                mock=False,
            )
        finally:
            for sp in staged_paths:
                try:
                    if sp.is_file() and not sp.is_symlink():
                        sp.unlink()
                except Exception:
                    pass

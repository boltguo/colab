"""H3 Character Swap (MiniMax-H3 Ref2VA + FL2V Turbo8 + Character Swap V1.5 + SAM 3.1) runner."""
from __future__ import annotations

from fractions import Fraction
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

from ...core.comfy_client import ComfyClient
from ...core.security import ensure_safe_dir, ensure_safe_path
from ...core.storage import MediaStorage
from .schemas import (
    DEFAULT_MASK_EXPANSION_PX,
    DEFAULT_SHIFT_AUDIO,
    DEFAULT_SHIFT_VIDEO,
    DEFAULT_SWAP_SCHEDULER,
    DEFAULT_SWAP_SIGMAS,
    DEFAULT_SWAP_STEPS,
    HISTORY_OVERLAP_FRAMES,
    H3CharacterSwapGenerateRequest,
    H3CharacterSwapResult,
    MAX_CLIP_DURATION_SEC,
    NATIVE_FPS,
    VideoOutputFormat,
    build_swap_prompt,
    compute_swap_dimensions,
    plan_swap_windows,
)

ProgressFn = Callable[[float, str], None]

UNET_FILENAME = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
TURBO_LORA_FILENAME = "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
PIKA_LORA_FILENAME = TURBO_LORA_FILENAME
SWAP_LORA_FILENAME = "h3_character_swap_v1.5.safetensors"
SAM_CHECKPOINT_FILENAME = "sam3.1_multiplex_fp16.safetensors"
CLIP_FILENAME = "qwen3vl_32b_minimax_h3_int8_convrot.safetensors"
VIDEO_VAE_FILENAME = "minimax_h3_video_vae_fp16.safetensors"
AUDIO_VAE_FILENAME = "minimax_h3_audio_vae_fp32.safetensors"


def _probe_video_meta(path: Path) -> Tuple[int, int, float, float, bool]:
    """Probe (width, height, duration_sec, fps, has_audio) via ffprobe."""
    ensure_safe_path(path)
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        raise RuntimeError("未找到 ffprobe，无法读取视频信息；请先安装 ffmpeg 后重试。")
    if not path.is_file():
        raise ValueError("源视频文件不存在，请重新上传。")
    try:
        proc = subprocess.run(
            [
                ffprobe_bin,
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,width,height,r_frame_rate,avg_frame_rate,duration,nb_frames:stream_tags=rotate:stream_side_data=rotation:format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        payload = json.loads(proc.stdout or "{}")
        streams = payload.get("streams") or []
        fmt = payload.get("format") or {}
        video = next((st for st in streams if st.get("codec_type") == "video"), None)
        if not video:
            raise ValueError("文件中没有视频画面。")
        width, height = int(video.get("width") or 0), int(video.get("height") or 0)
        rotations = [item.get("rotation") for item in video.get("side_data_list", [])]
        rotations.append((video.get("tags") or {}).get("rotate"))
        for raw_rotation in rotations:
            try:
                rotation = float(raw_rotation)
                if not math.isfinite(rotation):
                    continue
                if math.isclose(rotation % 180, 90, abs_tol=0.01):
                    width, height = height, width
                break
            except (TypeError, ValueError):
                continue
        fps = 0.0
        for rate in (video.get("avg_frame_rate"), video.get("r_frame_rate")):
            try:
                candidate = float(Fraction(str(rate)))
                if math.isfinite(candidate) and candidate > 0:
                    fps = candidate
                    break
            except (ValueError, ZeroDivisionError):
                continue
        duration = 0.0
        for raw_duration in (video.get("duration"), fmt.get("duration")):
            try:
                candidate = float(raw_duration)
                if math.isfinite(candidate) and candidate > 0:
                    duration = candidate
                    break
            except (TypeError, ValueError):
                continue
        if duration <= 0 and fps > 0:
            try:
                duration = float(video.get("nb_frames") or 0) / fps
            except (TypeError, ValueError):
                pass
        if min(width, height) < 2 or fps <= 0 or not math.isfinite(duration) or duration <= 0:
            raise ValueError("视频缺少有效的画幅、帧率或时长。")
        has_audio = any(st.get("codec_type") == "audio" for st in streams)
        return width, height, duration, fps, has_audio
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("无法读取源视频，请重新上传可播放的 MP4、WebM、MOV 或 MKV 文件。") from exc


def _is_valid_history_frames(history_frames: int) -> bool:
    return history_frames == 1 or (history_frames >= 5 and (history_frames - 5) % 17 == 0)


def build_character_swap_graph(
    *,
    unet_name: str,
    staged_source: str,
    staged_refs: List[str],
    prompt: str,
    padded_frames: int,
    width: int,
    height: int,
    seed: int,
    mode: str = "single",
    turbo_lora_name: str = TURBO_LORA_FILENAME,
    swap_lora_name: str = SWAP_LORA_FILENAME,
    sam_ckpt_name: str = SAM_CHECKPOINT_FILENAME,
    turbo_lora_strength: Optional[float] = None,
    pika_lora_strength: Optional[float] = None,
    swap_lora_strength: float = 1.0,
    shift_video: float = DEFAULT_SHIFT_VIDEO,
    shift_audio: float = DEFAULT_SHIFT_AUDIO,
    ref_image_size: str = "match",
    sampler_name: str = "er_sde",
    scheduler: str = DEFAULT_SWAP_SCHEDULER,
    steps: int = DEFAULT_SWAP_STEPS,
    sigmas: str = DEFAULT_SWAP_SIGMAS,
    keyframe_until: float = 0.9,
    enable_edit_mask: bool = True,
    mask_subject_prompt: str = "person",
    mask_selection: str = "largest",
    mask_index: int = 0,
    mask_expansion_px: int = DEFAULT_MASK_EXPANSION_PX,
    keep_audio: bool = True,
    filename_prefix: str = "h3_character_swap/window",
    staged_history: Optional[str] = None,
    history_frames: int = 0,
    window_guides: Optional[List[Tuple[str, int]]] = None,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str], str]:
    """Assemble an executable ComfyUI API graph for Ref2VA + V1.5 + SAM 3.1 character swap."""
    del sigmas, keyframe_until  # Retained for API/signature backward compatibility.
    if len(staged_refs) < 1:
        raise ValueError("至少需要 1 张人物参考图。")
    if history_frames and (not _is_valid_history_frames(history_frames) or not staged_history):
        raise ValueError("接续窗口需要提供有效的历史重叠视频（1 帧或 17k+5 帧）。")

    effective_turbo_strength = float(
        turbo_lora_strength
        if turbo_lora_strength is not None
        else (pika_lora_strength if pika_lora_strength is not None else 1.0)
    )

    def node(class_type: str, **inputs: Any) -> Dict[str, Any]:
        return {"class_type": class_type, "inputs": inputs}

    graph: Dict[str, Dict[str, Any]] = {
        "model": node("UNETLoader", unet_name=unet_name, weight_dtype="default"),
        "shift": node(
            "MiniMaxH3SigmaShift",
            model=["model", 0],
            shift_video=float(shift_video),
            shift_audio=float(shift_audio),
        ),
        "lora_turbo": node(
            "LoraLoaderModelOnly",
            model=["shift", 0],
            lora_name=turbo_lora_name,
            strength_model=effective_turbo_strength,
        ),
        "lora_swap": node(
            "LoraLoaderModelOnly",
            model=["lora_turbo", 0],
            lora_name=swap_lora_name,
            strength_model=float(swap_lora_strength),
        ),
        "clip": node(
            "CLIPLoader", clip_name=CLIP_FILENAME, type="minimax", device="default"
        ),
        "vae": node("VAELoader", vae_name=VIDEO_VAE_FILENAME),
        "source": node("LoadVideo", file=staged_source),
        "frames": node("GetVideoComponents", video=["source", 0]),
    }

    cond_inputs: Dict[str, Any] = {
        "clip": ["clip", 0],
        "vae": ["vae", 0],
        "prompt": prompt,
        "width": int(width),
        "height": int(height),
        "length": int(padded_frames),
        "ref_image_size": ref_image_size,
        "ref_videos.ref_video_0": ["frames", 0],
    }
    if keep_audio:
        graph["audio_vae"] = node("VAELoader", vae_name=AUDIO_VAE_FILENAME)
        cond_inputs["audio_vae"] = ["audio_vae", 0]
        cond_inputs["ref_video_audios.ref_video_audio_0"] = ["frames", 1]

    for idx, ref_name in enumerate(staged_refs, 1):
        ref_id = f"reference_{idx}"
        graph[ref_id] = node("LoadImage", image=ref_name)
        cond_inputs[f"ref_images.ref_image_{idx - 1}"] = [ref_id, 0]

    graph["conditioning"] = {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": cond_inputs}

    pos_ref: List[Any] = ["conditioning", 0]
    lat_ref: List[Any] = ["conditioning", 1]

    if enable_edit_mask:
        max_subjects = len(staged_refs) if mode == "multi" else 1
        sel_mode = "top_n" if (mode == "multi" and max_subjects > 1) else mask_selection
        graph["sam"] = node("CheckpointLoaderSimple", ckpt_name=sam_ckpt_name)
        graph["sam_subject"] = node(
            "CLIPTextEncode", clip=["sam", 1], text=(mask_subject_prompt or "person")
        )
        graph["sam_first_frame"] = node(
            "ImageFromBatch", image=["frames", 0], batch_index=0, length=1
        )
        graph["sam_detect"] = node(
            "SAM3_Detect",
            model=["sam", 0],
            image=["sam_first_frame", 0],
            conditioning=["sam_subject", 0],
            threshold=0.3,
            refine_iterations=2,
            individual_masks=True,
        )
        graph["sam_select"] = node(
            "H3SwapSelectMask",
            masks=["sam_detect", 0],
            selection=sel_mode,
            index=int(mask_index),
            max_subjects=int(max_subjects),
        )
        graph["sam_track"] = node(
            "SAM3_VideoTrack",
            images=["frames", 0],
            model=["sam", 0],
            initial_mask=["sam_select", 0],
            conditioning=["sam_subject", 0],
            detection_threshold=0.3,
            max_objects=int(max_subjects),
            detect_interval=1,
        )
        graph["sam_mask"] = node(
            "SAM3_TrackToMask", track_data=["sam_track", 0], object_indices=""
        )
        graph["sam_expand"] = node(
            "H3SwapExpandMask",
            masks=["sam_mask", 0],
            images=["frames", 0],
            expansion_px=int(mask_expansion_px),
        )
        graph["encode_source"] = node("VAEEncode", pixels=["frames", 0], vae=["vae", 0])
        graph["edit_mask"] = node(
            "H3SwapApplyEditMask",
            latent=lat_ref,
            source_latent=["encode_source", 0],
            mask=["sam_expand", 0],
        )
        lat_ref = ["edit_mask", 0]

    if history_frames and staged_history:
        graph["history_video"] = node("LoadVideo", file=staged_history)
        graph["history_components"] = node("GetVideoComponents", video=["history_video", 0])
        graph["history"] = node(
            "MiniMaxH3AddGuide",
            positive=pos_ref,
            latent=lat_ref,
            vae=["vae", 0],
            image=["history_components", 0],
            frame_idx=0,
        )
        pos_ref = ["history", 0]

    for idx, (guide_name, local_frame_idx) in enumerate(window_guides or [], 1):
        img_id = f"guide_image_{idx}"
        scale_id = f"guide_scale_{idx}"
        guide_id = f"guide_apply_{idx}"
        graph[img_id] = node("LoadImage", image=guide_name)
        graph[scale_id] = node(
            "ImageScale",
            image=[img_id, 0],
            upscale_method="lanczos",
            width=int(width),
            height=int(height),
            crop="center",
        )
        graph[guide_id] = node(
            "MiniMaxH3AddGuide",
            positive=pos_ref,
            latent=lat_ref,
            vae=["vae", 0],
            image=[scale_id, 0],
            frame_idx=int(local_frame_idx),
        )
        pos_ref = [guide_id, 0]

    graph.update(
        {
            "noise": node("RandomNoise", noise_seed=int(seed)),
            "guider": node("BasicGuider", model=["lora_swap", 0], conditioning=pos_ref),
            "sampler": node("KSamplerSelect", sampler_name=sampler_name),
            "sigmas": node(
                "BasicScheduler",
                model=["lora_swap", 0],
                scheduler=scheduler,
                steps=int(steps),
                denoise=1.0,
            ),
            "sample": node(
                "SamplerCustomAdvanced",
                noise=["noise", 0],
                guider=["guider", 0],
                sampler=["sampler", 0],
                sigmas=["sigmas", 0],
                latent_image=lat_ref,
            ),
            "separate": node("LTXVSeparateAVLatent", av_latent=["sample", 0]),
            "decode": node("VAEDecode", samples=["separate", 0], vae=["vae", 0]),
            "create_video": node(
                "CreateVideo",
                images=["decode", 0],
                fps=float(NATIVE_FPS),
            ),
            "save": node(
                "SaveVideo",
                video=["create_video", 0],
                filename_prefix=filename_prefix,
                format="mp4",
                **{"format.codec": "h264", "format.codec.encoding": "auto"},
            ),
        }
    )

    labels = {
        "model": "加载 MiniMax-H3 Ref2VA 主模型",
        "shift": "设置音画流偏移 (12 / 3)",
        "lora_turbo": "挂载 FL2V Turbo 8 步加速权重",
        "lora_swap": "挂载 Character Swap V1.5 人物替换权重",
        "clip": "加载 Qwen3-VL 多模态编码器",
        "conditioning": "编码原视频动作与参考人物特征",
        "sam_detect": "SAM 3.1 检测目标人物",
        "sam_track": "SAM 3.1 跟踪人物全身遮罩",
        "edit_mask": "锁定原视频背景与非目标区域",
        "history": "挂载前窗延续历史帧",
        "sample": f"执行 {int(steps)} 步人物替换扩散采样",
        "decode": "解码替换视频帧",
        "save": "封装窗口输出视频",
    }
    return graph, labels, "save"


build_viggle_remake_graph = build_character_swap_graph


def _encode_container(
    src_video: Path,
    dest: Path,
    *,
    fmt: VideoOutputFormat,
    audio_source: Optional[Path] = None,
) -> None:
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("视频封装需要 FFmpeg，请先安装 ffmpeg。")
    cmd: List[str] = [
        ffmpeg_bin,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(src_video),
    ]
    if audio_source is not None:
        cmd.extend(["-i", str(audio_source), "-map", "0:v:0", "-map", "1:a:0?"])
    else:
        cmd.extend(["-map", "0:v:0"])
        if audio_source is None:
            cmd.append("-an")

    if fmt == "webm":
        cmd.extend(["-c:v", "libvpx-vp9", "-b:v", "2200k", "-pix_fmt", "yuv420p"])
        if audio_source is not None:
            cmd.extend(["-c:a", "libopus", "-b:a", "128k"])
    else:
        cmd.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p"])
        if fmt == "mp4":
            cmd.extend(["-movflags", "+faststart"])
        if audio_source is not None:
            cmd.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])

    cmd.append(str(dest))
    subprocess.run(cmd, check=True, timeout=600)


class H3CharacterSwapRunner:
    """Orchestrate MiniMax-H3 Character Swap on headless ComfyUI or mock mode."""

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

    def release_vram(self) -> None:
        if not self.mock_mode:
            self.comfy.free_memory(unload_models=True, free_memory=True)

    def _resolve_model_choice(self, node_name: str, field_name: str, default_name: str) -> str:
        try:
            info = self.comfy.get_json(f"/object_info/{node_name}", timeout=8.0)
            choices = (
                info.get(node_name, {})
                .get("input", {})
                .get("required", {})
                .get(field_name, [[]])[0]
            )
            if default_name in choices:
                return default_name
            alt = Path(default_name).name
            if alt in choices:
                return alt
            for candidate in choices:
                if Path(str(candidate)).name == alt:
                    return str(candidate)
        except Exception:
            pass
        return default_name

    def _resolve_unet_name(self) -> str:
        return self._resolve_model_choice("UNETLoader", "unet_name", UNET_FILENAME)

    def _resolve_lora_name(self, default_name: str) -> str:
        return self._resolve_model_choice("LoraLoaderModelOnly", "lora_name", default_name)

    def _resolve_sam_name(self) -> str:
        return self._resolve_model_choice(
            "CheckpointLoaderSimple", "ckpt_name", SAM_CHECKPOINT_FILENAME
        )

    def _prepare_source_clip(
        self,
        src_path: Path,
        dest_clip: Path,
        *,
        out_w: int,
        out_h: int,
        start_time_sec: float,
        duration_sec: float,
        keep_audio: bool,
        src_has_audio: bool,
    ) -> Tuple[int, float]:
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            raise RuntimeError("视频预处理需要 FFmpeg，请先安装 ffmpeg。")
        cmd = [
            ffmpeg_bin,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{start_time_sec:.6f}",
            "-i",
            str(src_path),
            "-t",
            f"{duration_sec:.6f}",
            "-vf",
            (
                f"fps={NATIVE_FPS},"
                f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={out_w}:{out_h},setsar=1"
            ),
            "-r",
            str(NATIVE_FPS),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "12",
            "-pix_fmt",
            "yuv420p",
        ]
        if keep_audio and src_has_audio:
            cmd.extend(["-map", "0:v:0", "-map", "0:a:0?", "-c:a", "aac", "-b:a", "192k"])
        else:
            cmd.extend(["-map", "0:v:0", "-an"])
        cmd.append(str(dest_clip))
        subprocess.run(cmd, check=True, timeout=300)

        _, _, actual_dur, _, _ = _probe_video_meta(dest_clip)
        proc = subprocess.run(
            [
                shutil.which("ffprobe") or "ffprobe",
                "-v",
                "error",
                "-count_frames",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=nb_read_frames,nb_frames",
                "-of",
                "json",
                str(dest_clip),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        stream = (json.loads(proc.stdout or "{}").get("streams") or [{}])[0]
        raw_count = stream.get("nb_read_frames") or stream.get("nb_frames")
        frame_count = int(raw_count) if str(raw_count).isdigit() else max(1, round(actual_dur * NATIVE_FPS))
        return frame_count, frame_count / float(NATIVE_FPS)

    def _prepare_window_video(
        self,
        prepared_source: Path,
        dest_window: Path,
        *,
        frame_start: int,
        frame_count: int,
        padded_frames: int,
        keep_audio: bool,
        has_audio: bool,
    ) -> None:
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            raise RuntimeError("窗口视频切分需要 FFmpeg。")
        frame_end = frame_start + frame_count - 1
        pad_count = max(0, padded_frames - frame_count)
        vf = f"select='between(n\\,{frame_start}\\,{frame_end})',setpts=PTS-STARTPTS"
        if pad_count > 0:
            vf += f",tpad=stop_mode=clone:stop_duration={pad_count / float(NATIVE_FPS):.6f}"
        cmd = [
            ffmpeg_bin,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(prepared_source),
            "-vf",
            vf,
            "-frames:v",
            str(padded_frames),
            "-r",
            str(NATIVE_FPS),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "12",
            "-pix_fmt",
            "yuv420p",
        ]
        if keep_audio and has_audio:
            t0 = frame_start / float(NATIVE_FPS)
            tdur = padded_frames / float(NATIVE_FPS)
            cmd.extend(
                [
                    "-af",
                    f"atrim=start={t0:.6f}:duration={tdur:.6f},asetpts=PTS-STARTPTS",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                ]
            )
        else:
            cmd.append("-an")
        cmd.append(str(dest_window))
        subprocess.run(cmd, check=True, timeout=180)

    def _extract_frame_slice(
        self,
        src_video: Path,
        dest_video: Path,
        *,
        start_frame: int,
        count: int,
    ) -> None:
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            raise RuntimeError("视频切片需要 FFmpeg。")
        end_frame = start_frame + count - 1
        subprocess.run(
            [
                ffmpeg_bin,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(src_video),
                "-vf",
                f"select='between(n\\,{start_frame}\\,{end_frame})',setpts=PTS-STARTPTS",
                "-frames:v",
                str(count),
                "-r",
                str(NATIVE_FPS),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "10",
                "-pix_fmt",
                "yuv420p",
                str(dest_video),
            ],
            check=True,
            timeout=180,
        )

    def _concat_clips(self, clips: List[Path], dest_video: Path, work_dir: Path) -> None:
        if len(clips) == 1:
            shutil.copy2(clips[0], dest_video)
            return
        list_file = work_dir / "concat_list.txt"
        list_file.write_text(
            "".join(f"file '{clip.resolve()}'\n" for clip in clips),
            encoding="utf-8",
        )
        subprocess.run(
            [
                shutil.which("ffmpeg") or "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "14",
                "-pix_fmt",
                "yuv420p",
                str(dest_video),
            ],
            check=True,
            timeout=300,
        )

    def execute_task(self, raw_params: Dict[str, Any], on_progress: ProgressFn) -> Dict[str, Any]:
        started = time.monotonic()
        req = H3CharacterSwapGenerateRequest.model_validate(raw_params)

        on_progress(0.03, "正在读取源视频与人物参考素材...")
        src_path = self.storage.resolve_input_ref(req.source_video)
        src_w, src_h, src_dur, src_fps, src_has_audio = _probe_video_meta(src_path)

        ref_paths = [self.storage.resolve_input_ref(slot.image) for slot in req.characters]
        guide_paths = [self.storage.resolve_input_ref(slot.image) for slot in req.guide_frames]

        out_w, out_h = compute_swap_dimensions(
            src_w, src_h, req.resolution_tier, preserve_aspect=req.preserve_aspect
        )
        start_sec = min(req.start_time_sec, max(0.0, src_dur - 0.1))
        available_dur = max(0.25, src_dur - start_sec)
        target_dur = (
            min(available_dur, MAX_CLIP_DURATION_SEC)
            if req.duration_sec <= 0
            else min(available_dur, req.duration_sec)
        )

        effective_prompt = build_swap_prompt(
            req.mode,
            req.characters,
            req.prompt,
            keep_audio=req.keep_audio and src_has_audio,
        )
        actual_seed = req.seed if req.seed > 0 else secrets.randbelow(2_147_483_647) + 1
        out_ext_map: Dict[VideoOutputFormat, str] = {"mp4": ".mp4", "webm": ".webm", "mkv": ".mkv"}
        out_ext = out_ext_map[req.output_format]

        with tempfile.TemporaryDirectory(prefix="h3_swap_") as tmp:
            work_dir = Path(tmp)
            prepared_source = work_dir / "prepared_source.mp4"
            on_progress(0.08, "正在统一对齐源视频到 24 fps 与模型画布尺寸...")
            total_frames, actual_dur = self._prepare_source_clip(
                src_path,
                prepared_source,
                out_w=out_w,
                out_h=out_h,
                start_time_sec=start_sec,
                duration_sec=target_dur,
                keep_audio=req.keep_audio,
                src_has_audio=src_has_audio,
            )

            windows = plan_swap_windows(
                total_frames,
                max_window_frames=req.window_frames,
                overlap_frames=HISTORY_OVERLAP_FRAMES,
            )
            has_audio = bool(req.keep_audio and src_has_audio)

            if self.mock_mode:
                mock_steps = min(req.steps, 10)
                for step in range(1, mock_steps + 1):
                    time.sleep(0.05)
                    on_progress(
                        0.15 + 0.72 * (step / float(mock_steps)),
                        f"[Mock] H3 Character Swap 采样（步数 {step}/{mock_steps} · {len(req.characters)} 位角色 · {len(windows)} 个时间窗）...",
                    )
                on_progress(0.90, "[Mock] 正在封装替换预览视频...")
                fname, dest = self.storage.allocate_output_path("h3_character_swap", out_ext)
                preview_src = work_dir / "mock_preview.mp4"
                ffmpeg_bin = shutil.which("ffmpeg")
                if ffmpeg_bin:
                    subprocess.run(
                        [
                            ffmpeg_bin,
                            "-nostdin",
                            "-hide_banner",
                            "-loglevel",
                            "error",
                            "-y",
                            "-i",
                            str(prepared_source),
                            "-vf",
                            "eq=saturation=1.18:contrast=1.05",
                            "-c:v",
                            "libx264",
                            "-preset",
                            "ultrafast",
                            "-crf",
                            "22",
                            "-pix_fmt",
                            "yuv420p",
                            *(
                                ["-c:a", "aac", "-b:a", "128k"]
                                if has_audio
                                else ["-an"]
                            ),
                            str(preview_src),
                        ],
                        check=True,
                        timeout=60,
                    )
                    if req.output_format == "mp4":
                        shutil.copy2(preview_src, dest)
                    else:
                        _encode_container(
                            preview_src,
                            dest,
                            fmt=req.output_format,
                            audio_source=prepared_source if has_audio else None,
                        )
                else:
                    dest.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom\x00\x00\x00\x08free")

                return H3CharacterSwapResult(
                    video_url=f"/api/v1/outputs/{fname}",
                    filename=fname,
                    format=req.output_format,
                    width=out_w,
                    height=out_h,
                    fps=NATIVE_FPS,
                    frame_count=total_frames,
                    duration_sec=round(actual_dur, 3),
                    has_audio=has_audio,
                    size_bytes=dest.stat().st_size,
                    seed=actual_seed,
                    mode=req.mode,
                    character_count=len(req.characters),
                    window_count=len(windows),
                    resolution_tier=req.resolution_tier,
                    source_video_ref=req.source_video,
                    input_width=src_w,
                    input_height=src_h,
                    input_fps=round(src_fps, 3),
                    input_start_time=round(start_sec, 3),
                    effective_prompt=effective_prompt,
                    elapsed_sec=round(time.monotonic() - started, 2),
                    mock=True,
                ).model_dump()

            staged_paths: List[Path] = []
            try:
                unet_name = self._resolve_unet_name()
                turbo_lora_name = self._resolve_lora_name(TURBO_LORA_FILENAME)
                swap_lora_name = self._resolve_lora_name(SWAP_LORA_FILENAME)
                sam_ckpt_name = self._resolve_sam_name() if req.enable_edit_mask else SAM_CHECKPOINT_FILENAME
                staged_refs: List[str] = []
                for idx, ref_path in enumerate(ref_paths, 1):
                    name = self.comfy.stage_input_file(ref_path, prefix=f"swap_ref_{idx}")
                    staged_refs.append(name)
                    staged_paths.append(self.comfy.input_dir / name)

                staged_guides: List[Tuple[str, int]] = []
                for idx, (g_path, g_slot) in enumerate(zip(guide_paths, req.guide_frames), 1):
                    name = self.comfy.stage_input_file(g_path, prefix=f"swap_guide_{idx}")
                    staged_guides.append((name, g_slot.frame_index))
                    staged_paths.append(self.comfy.input_dir / name)

                window_outputs: List[Path] = []
                history_clip_path: Optional[Path] = None
                win_total = len(windows)
                for w_idx, win in enumerate(windows):
                    p0 = 0.14 + 0.78 * (w_idx / win_total)
                    p1 = 0.14 + 0.78 * ((w_idx + 1) / win_total)
                    hist_n = win["history_frames"]
                    src_start = win["source_start"]
                    new_n = win["source_frames"]
                    padded_n = win["padded_frames"]
                    win_src_start = max(0, src_start - hist_n)
                    win_src_frames = hist_n + new_n

                    win_input_path = work_dir / f"win_src_{w_idx}.mp4"
                    self._prepare_window_video(
                        prepared_source,
                        win_input_path,
                        frame_start=win_src_start,
                        frame_count=win_src_frames,
                        padded_frames=padded_n,
                        keep_audio=has_audio,
                        has_audio=has_audio,
                    )
                    staged_src_name = f"studio_swap_src_{w_idx}_{uuid.uuid4().hex[:10]}.mp4"
                    shutil.copy2(win_input_path, ensure_safe_path(self.comfy.input_dir / staged_src_name, stop_at=self.comfy.input_dir))
                    staged_paths.append(self.comfy.input_dir / staged_src_name)

                    staged_hist_name: Optional[str] = None
                    if hist_n and history_clip_path is not None:
                        staged_hist_name = f"studio_swap_hist_{w_idx}_{uuid.uuid4().hex[:10]}.mp4"
                        shutil.copy2(
                            history_clip_path,
                            ensure_safe_path(self.comfy.input_dir / staged_hist_name, stop_at=self.comfy.input_dir),
                        )
                        staged_paths.append(self.comfy.input_dir / staged_hist_name)

                    local_guides: List[Tuple[str, int]] = []
                    for g_name, g_abs_frame in staged_guides:
                        if src_start <= g_abs_frame < src_start + new_n:
                            local_guides.append((g_name, hist_n + (g_abs_frame - src_start)))

                    graph, labels, save_id = build_character_swap_graph(
                        mode=req.mode,
                        unet_name=unet_name,
                        turbo_lora_name=turbo_lora_name,
                        swap_lora_name=swap_lora_name,
                        sam_ckpt_name=sam_ckpt_name,
                        staged_source=staged_src_name,
                        staged_refs=staged_refs,
                        prompt=effective_prompt,
                        padded_frames=padded_n,
                        width=out_w,
                        height=out_h,
                        seed=actual_seed + w_idx,
                        turbo_lora_strength=req.turbo_lora_strength,
                        swap_lora_strength=req.swap_lora_strength,
                        shift_video=req.shift_video,
                        shift_audio=req.shift_audio,
                        ref_image_size=req.ref_image_size,
                        sampler_name=req.sampler_name,
                        scheduler=req.scheduler,
                        steps=req.steps,
                        sigmas=req.sigmas,
                        keyframe_until=req.keyframe_until,
                        enable_edit_mask=req.enable_edit_mask,
                        mask_subject_prompt=req.mask_subject_prompt,
                        mask_selection=req.mask_selection,
                        mask_index=req.mask_index,
                        mask_expansion_px=req.mask_expansion_px,
                        keep_audio=has_audio,
                        staged_history=staged_hist_name,
                        history_frames=hist_n,
                        window_guides=local_guides,
                    )
                    on_progress(
                        p0,
                        f"正在渲染时间窗 {w_idx + 1}/{win_total}（共 {new_n} 新帧）...",
                    )
                    entry = self.comfy.run_prompt(
                        graph,
                        on_progress=on_progress,
                        node_labels=labels,
                        progress_range=(p0, p1),
                        timeout_sec=3600.0,
                    )
                    outputs = entry.get("outputs") or {}
                    save_out = outputs.get(save_id) or {}
                    raw_videos = save_out.get("images") or save_out.get("videos") or save_out.get("gifs") or []
                    if not raw_videos:
                        for node_out in outputs.values():
                            if isinstance(node_out, dict):
                                raw_videos = node_out.get("images") or node_out.get("videos") or node_out.get("gifs") or []
                                if raw_videos:
                                    break
                    if not raw_videos:
                        raise RuntimeError(f"时间窗 {w_idx + 1} 推理完成，但未生成输出视频。")

                    comfy_video = self.comfy.resolve_output_file(raw_videos[0])
                    trimmed_win = work_dir / f"win_trimmed_{w_idx}.mp4"
                    self._extract_frame_slice(
                        comfy_video, trimmed_win, start_frame=hist_n, count=new_n
                    )
                    window_outputs.append(trimmed_win)

                    if w_idx + 1 < win_total:
                        next_hist = work_dir / f"win_next_hist_{w_idx}.mp4"
                        hist_start = max(0, (hist_n + new_n) - HISTORY_OVERLAP_FRAMES)
                        self._extract_frame_slice(
                            comfy_video,
                            next_hist,
                            start_frame=hist_start,
                            count=HISTORY_OVERLAP_FRAMES,
                        )
                        history_clip_path = next_hist

                on_progress(0.94, "正在拼接替换片段并合成最终音画视频...")
                merged_video = work_dir / "merged_video.mp4"
                self._concat_clips(window_outputs, merged_video, work_dir)

                fname, dest = self.storage.allocate_output_path("h3_character_swap", out_ext)
                _encode_container(
                    merged_video,
                    dest,
                    fmt=req.output_format,
                    audio_source=prepared_source if has_audio else None,
                )

                return H3CharacterSwapResult(
                    video_url=f"/api/v1/outputs/{fname}",
                    filename=fname,
                    format=req.output_format,
                    width=out_w,
                    height=out_h,
                    fps=NATIVE_FPS,
                    frame_count=total_frames,
                    duration_sec=round(actual_dur, 3),
                    has_audio=has_audio,
                    size_bytes=dest.stat().st_size,
                    seed=actual_seed,
                    mode=req.mode,
                    character_count=len(req.characters),
                    window_count=win_total,
                    resolution_tier=req.resolution_tier,
                    source_video_ref=req.source_video,
                    input_width=src_w,
                    input_height=src_h,
                    input_fps=round(src_fps, 3),
                    input_start_time=round(start_sec, 3),
                    effective_prompt=effective_prompt,
                    elapsed_sec=round(time.monotonic() - started, 2),
                    mock=False,
                ).model_dump()
            finally:
                for staged in staged_paths:
                    try:
                        if staged.is_file() and not staged.is_symlink():
                            staged.unlink()
                    except Exception:
                        pass

"""Native Python IndexTTS-2.5 inference runner (full controllability & mastering)."""
import array
from contextlib import contextmanager
import gc
import math
import os
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
import wave

from backend.core.config import AppSettings
from backend.core.security import ensure_safe_path
from backend.core.storage import MediaStorage
from .schemas import IndexTTSGenerateRequest, compute_effective_emo_vector

ProgressCallback = Callable[[float, str], None]

REQUIRED_MODEL_FILES = [
    "config.yaml",
    "gpt.pth",
    "s2mel.pth",
    "codec.pth",
    "wav2vec2bert_stats.pt",
    "feat1.pt",
    "feat2.pt",
    "multilingual_zh_ja_yue_char_del.tiktoken",
]


def _resolve_model_dir() -> Path:
    env_dir = os.environ.get("INDEXTTS_MODEL_DIR", "").strip()
    candidates = [
        Path(env_dir) if env_dir else None,
        Path("/content/models/IndexTTS-2.5"),
        Path("/content/ComfyUI/models/TTS/IndexTTS-2.5"),
    ]
    for candidate in candidates:
        if candidate and candidate.is_dir() and not candidate.is_symlink():
            return candidate
    return Path(env_dir) if env_dir else Path("/content/models/IndexTTS-2.5")


def _resolve_src_dir() -> Optional[Path]:
    env_src = os.environ.get("INDEXTTS_SRC_DIR", "").strip()
    candidates = [
        Path(env_src) if env_src else None,
        Path("/content/index-tts"),
    ]
    for candidate in candidates:
        if candidate and (candidate / "indextts").is_dir() and not candidate.is_symlink():
            return candidate
    return None


def _install_transformers_compat_shim() -> None:
    """Ensure transformers.modeling_utils.SequenceSummary exists on newer Transformers."""
    try:
        import torch.nn as nn  # type: ignore
        import transformers.modeling_utils as mu  # type: ignore
    except Exception:
        return

    if hasattr(mu, "SequenceSummary"):
        return

    class SequenceSummary(nn.Module):
        def __init__(self, config: Any) -> None:
            super().__init__()
            summary_type = getattr(config, "summary_type", "last")
            self.summary_type = summary_type
            use_proj = getattr(config, "summary_use_proj", True)
            proj_to_labels = getattr(config, "summary_proj_to_labels", True)
            num_labels = getattr(config, "num_labels", 0)
            hidden_size = getattr(config, "hidden_size", getattr(config, "n_embd", 1024))
            out_dim = num_labels if (proj_to_labels and num_labels > 0) else hidden_size
            self.summary = nn.Linear(hidden_size, out_dim) if use_proj else nn.Identity()
            first_dropout = getattr(config, "summary_first_dropout", 0.0)
            self.first_dropout = nn.Dropout(first_dropout) if first_dropout > 0 else nn.Identity()
            self.last_dropout = nn.Identity()
            self.activation = nn.Identity()

        def forward(self, hidden_states: Any, cls_index: Any = None) -> Any:
            output = hidden_states[:, -1]
            output = self.first_dropout(output)
            output = self.summary(output)
            output = self.activation(output)
            return self.last_dropout(output)

    setattr(mu, "SequenceSummary", SequenceSummary)


def _format_clock(seconds: float, mode: str = "compact") -> str:
    total_ms = max(0, round(float(seconds) * 1000))
    total_seconds, ms = divmod(total_ms, 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, sec = divmod(remainder, 60)
    if mode == "srt":
        return f"{hours:02d}:{minutes:02d}:{sec:02d},{ms:03d}"
    if mode == "vtt":
        return f"{hours:02d}:{minutes:02d}:{sec:02d}.{ms:03d}"
    return f"{minutes}:{sec:02d}.{ms:03d}"


def _estimate_segments(text: str, max_tokens_per_segment: int) -> List[str]:
    """Approximate punctuation-aware chunking matching IndexTTS2.split_text_by_tokens."""
    approx_char_budget = max(16, int(max_tokens_per_segment * 0.9))
    raw_parts = re.split(r"(?<=[，。！？、；：,\.!\?;:\n])", text)
    segments: List[str] = []
    current = ""
    for part in raw_parts:
        piece = part.strip()
        if not piece:
            continue
        if current and len(current) + len(piece) > approx_char_budget:
            segments.append(current)
            current = piece
        else:
            current = f"{current}{piece}" if current else piece
    if current:
        segments.append(current)
    return segments or [text.strip()]


def _build_subtitles(
    text: str,
    total_duration: float,
    max_tokens_per_segment: int = 120,
) -> Tuple[str, str, str, List[Dict[str, Any]]]:
    parts = re.split(r"([,，。！？!?；;：:\n])", text)
    sentences: List[str] = []
    idx = 0
    while idx < len(parts):
        seg = parts[idx]
        punct = parts[idx + 1] if idx + 1 < len(parts) else ""
        combined = (seg + punct).strip()
        if combined:
            sentences.append(combined)
        idx += 2
    if not sentences:
        sentences = _estimate_segments(text, max_tokens_per_segment)

    # Strip <word|pronunciation> markup into readable word for subtitles
    clean_sentences = [re.sub(r"<([^|>\n]+)\|[^>\n]+>", r"\1", s) for s in sentences]
    total_chars = max(1, sum(len(s) for s in clean_sentences))

    preview_lines: List[str] = []
    srt_blocks: List[str] = []
    vtt_blocks: List[str] = ["WEBVTT", ""]
    timeline_items: List[Dict[str, Any]] = []
    cursor = 0.0

    for i, sentence in enumerate(clean_sentences, start=1):
        ratio = len(sentence) / total_chars
        seg_dur = (
            total_duration * ratio
            if i < len(clean_sentences)
            else max(0.05, total_duration - cursor)
        )
        end_t = min(total_duration, cursor + seg_dur)
        preview_lines.append(f"[{_format_clock(cursor)} -> {_format_clock(end_t)}] {sentence}")
        srt_blocks.append(
            f"{i}\n{_format_clock(cursor, 'srt')} --> {_format_clock(end_t, 'srt')}\n{sentence}"
        )
        vtt_blocks.append(
            f"{_format_clock(cursor, 'vtt')} --> {_format_clock(end_t, 'vtt')}\n{sentence}\n"
        )
        timeline_items.append(
            {
                "index": i,
                "start_sec": round(cursor, 3),
                "end_sec": round(end_t, 3),
                "text": sentence,
            }
        )
        cursor = end_t

    return (
        "\n".join(preview_lines),
        "\n\n".join(srt_blocks),
        "\n".join(vtt_blocks).strip() + "\n",
        timeline_items,
    )


def _postprocess_pcm16(
    pcm_bytes: bytes,
    sample_rate: int,
    trim_silence: bool,
    tail_fade_ms: int,
) -> bytes:
    samples = array.array("h")
    samples.frombytes(pcm_bytes)
    if sys.byteorder != "little":
        samples.byteswap()

    n = len(samples)
    if n == 0:
        return pcm_bytes

    if trim_silence:
        threshold = 220  # ~ -43 dBFS
        pad = int(sample_rate * 0.035)
        first = 0
        while first < n and abs(samples[first]) < threshold:
            first += 1
        last = n - 1
        while last > first and abs(samples[last]) < threshold:
            last -= 1
        start_idx = max(0, first - pad)
        end_idx = min(n, last + pad + 1)
        if end_idx > start_idx:
            samples = samples[start_idx:end_idx]
            n = len(samples)

    if tail_fade_ms > 0 and n > 16:
        fade_samples = min(n, int(sample_rate * (tail_fade_ms / 1000.0)))
        if fade_samples > 1:
            start_fade = n - fade_samples
            for i in range(fade_samples):
                gain = 0.5 * (1.0 + math.cos(math.pi * (i / fade_samples)))
                idx = start_fade + i
                samples[idx] = int(round(samples[idx] * gain))

    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()


def _write_pcm16_wav(dest: Path, pcm_bytes: bytes, sample_rate: int) -> None:
    with wave.open(str(dest), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm_bytes)


def _read_wav_duration(wav_path: Path, fallback_bytes: int, sample_rate: int) -> float:
    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate() or sample_rate
            return float(frames) / max(1, rate)
    except Exception:
        return float(fallback_bytes // 2) / max(1, sample_rate)


def _encode_audio_file(
    pcm_bytes: bytes,
    sample_rate: int,
    requested_format: str,
    loudness_norm: bool,
    storage: MediaStorage,
    prefix: str,
) -> Tuple[str, Path, str, float]:
    ffmpeg_bin = shutil.which("ffmpeg")
    duration_sec = float(len(pcm_bytes) // 2) / max(1, sample_rate)

    if not ffmpeg_bin or (requested_format == "wav" and not loudness_norm):
        filename, dest_wav = storage.allocate_output_path(prefix, ".wav")
        _write_pcm16_wav(dest_wav, pcm_bytes, sample_rate)
        return filename, dest_wav, "wav", duration_sec

    ext_map = {"mp3": ".mp3", "flac": ".flac", "wav": ".wav"}
    target_fmt = requested_format if requested_format in ext_map else "wav"
    filename, dest_file = storage.allocate_output_path(prefix, ext_map[target_fmt])

    fd, tmp_wav = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    tmp_path = Path(tmp_wav)
    try:
        _write_pcm16_wav(tmp_path, pcm_bytes, sample_rate)
        cmd: List[str] = [ffmpeg_bin, "-y", "-loglevel", "error", "-i", str(tmp_path)]
        if loudness_norm:
            cmd.extend(["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"])
        if target_fmt == "mp3":
            cmd.extend(["-codec:a", "libmp3lame", "-qscale:a", "0"])
        elif target_fmt == "flac":
            cmd.extend(["-codec:a", "flac"])
        else:
            cmd.extend(["-codec:a", "pcm_s16le"])
        # loudnorm may upsample internally; keep the saved file and metadata aligned.
        cmd.extend(["-ar", str(sample_rate)])
        cmd.append(str(dest_file))
        subprocess.run(cmd, check=True)
        if target_fmt == "wav":
            duration_sec = _read_wav_duration(dest_file, len(pcm_bytes), sample_rate)
        return filename, dest_file, target_fmt, duration_sec
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@contextmanager
def _override_indextts_runtime_knobs(
    tts: Any,
    max_ref_seconds: float,
    diffusion_steps: int,
    inference_cfg_rate: float,
) -> Iterator[None]:
    """Temporarily override hardcoded internal knobs (15s ref window, 25 CFM steps, 0.7 CFG)."""
    orig_load_audio = getattr(tts, "_load_and_cut_audio", None)
    cfm_module = None
    orig_cfm_infer = None
    try:
        if hasattr(tts, "s2mel") and tts.s2mel is not None and "cfm" in tts.s2mel.models:
            cfm_module = tts.s2mel.models["cfm"]
            orig_cfm_infer = cfm_module.inference
    except Exception:
        cfm_module = None

    prev_ref_sec = getattr(tts, "_colab_last_max_ref_seconds", 15.0)
    if abs(prev_ref_sec - float(max_ref_seconds)) > 1e-3:
        for cache_attr in ("cache_spk_cond", "cache_emo_cond"):
            if hasattr(tts, cache_attr):
                setattr(tts, cache_attr, None)
    setattr(tts, "_colab_last_max_ref_seconds", float(max_ref_seconds))

    if orig_load_audio is not None and abs(float(max_ref_seconds) - 15.0) > 1e-3:
        def _patched_load_audio(audio_path: str, _max_sec: float, verbose: bool = False, sr: Any = None):
            return orig_load_audio(audio_path, float(max_ref_seconds), verbose=verbose, sr=sr)

        setattr(tts, "_load_and_cut_audio", _patched_load_audio)

    if cfm_module is not None and orig_cfm_infer is not None and (
        int(diffusion_steps) != 25 or abs(float(inference_cfg_rate) - 0.7) > 1e-4
    ):
        def _patched_cfm_inference(*args: Any, **kwargs: Any):
            mutable = list(args)
            if len(mutable) >= 6:
                mutable[5] = int(diffusion_steps)
            else:
                kwargs["n_timesteps"] = int(diffusion_steps)
            kwargs["inference_cfg_rate"] = float(inference_cfg_rate)
            return orig_cfm_infer(*mutable, **kwargs)

        cfm_module.inference = _patched_cfm_inference

    try:
        yield
    finally:
        if orig_load_audio is not None:
            setattr(tts, "_load_and_cut_audio", orig_load_audio)
        if cfm_module is not None and orig_cfm_infer is not None:
            cfm_module.inference = orig_cfm_infer


class IndexTTS25EngineManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: Dict[Tuple[bool, bool, bool, bool], Any] = {}

    @contextmanager
    def use_engine(self, *, auto_free_memory: bool = False, **kwargs: Any) -> Iterator[Any]:
        """Keep model loading, inference and release mutually exclusive."""
        with self._lock:
            try:
                yield self.get_engine(**kwargs)
            finally:
                if auto_free_memory:
                    self.release()

    def get_engine(
        self,
        use_bf16: bool,
        use_qwen_emo: bool,
        use_cuda_kernel: bool,
        use_torch_compile: bool,
        progress_cb: ProgressCallback,
    ) -> Any:
        key = (
            bool(use_bf16),
            bool(use_qwen_emo),
            bool(use_cuda_kernel),
            bool(use_torch_compile),
        )
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                return cached

            model_dir = ensure_safe_path(_resolve_model_dir())
            missing = [f for f in REQUIRED_MODEL_FILES if not (model_dir / f).is_file()]
            if missing:
                raise FileNotFoundError(
                    f"IndexTTS-2.5 模型目录 ({model_dir}) 缺少必需权重：{', '.join(missing)}。请先在 Colab 运行第 3 步下载模型。"
                )

            src_dir = _resolve_src_dir()
            if src_dir is not None:
                ensure_safe_path(src_dir)
                src_str = str(src_dir)
                if src_str not in sys.path:
                    sys.path.insert(0, src_str)

            _install_transformers_compat_shim()
            progress_cb(0.06, "正在加载 IndexTTS-2.5 模型权重至 GPU...")

            import torch  # type: ignore
            from indextts.infer_v2_5 import IndexTTS2  # type: ignore

            # A Colab runtime only needs one configuration resident at a time.
            # Otherwise toggling emotion/precision options retains entire models.
            self.release()
            on_cuda = bool(torch.cuda.is_available())
            bf16_ok = bool(use_bf16) and on_cuda and bool(torch.cuda.is_bf16_supported())
            tts = IndexTTS2(
                cfg_path=str(model_dir / "config.yaml"),
                model_dir=str(model_dir),
                device=None,
                use_bf16=bf16_ok,
                use_cuda_kernel=bool(use_cuda_kernel) and on_cuda,
                use_deepspeed=False,
                use_accel=False,
                use_torch_compile=bool(use_torch_compile) and on_cuda,
                use_qwen_emo=bool(use_qwen_emo),
            )
            self._cache[key] = tts
            return tts

    def release(self) -> Dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            return {"released_instances": 0, "busy": True}
        try:
            instances = list(self._cache.values())
            self._cache.clear()
            if not instances:
                return {"released_instances": 0, "busy": False}
            attrs = (
                "gpt", "semantic_model", "semantic_codec", "s2mel",
                "campplus_model", "bigvgan", "qwen_emo",
                "semantic_mean", "semantic_std", "emo_matrix", "spk_matrix",
                "cache_spk_cond", "cache_s2mel_style", "cache_s2mel_prompt",
                "cache_emo_cond", "cache_mel",
            )
            for inst in instances:
                for attr in attrs:
                    if hasattr(inst, attr):
                        setattr(inst, attr, None)

            gc.collect()
            try:
                import torch  # type: ignore
                if torch.cuda.is_available():
                    torch.cuda.synchronize()
                    torch.cuda.empty_cache()
            except Exception:
                pass
            return {"released_instances": len(instances), "busy": False}
        finally:
            self._lock.release()


ENGINE_MANAGER = IndexTTS25EngineManager()


def _run_mock_synthesis(
    req: IndexTTSGenerateRequest,
    actual_seed: int,
    effective_emo_vec: Optional[List[float]],
    storage: MediaStorage,
    progress_cb: ProgressCallback,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    est_segs = _estimate_segments(req.text, req.max_text_tokens_per_segment)
    stages = [
        (0.18, f"Mock 模式：文本正则化与分句（共 {len(est_segs)} 段）..."),
        (0.50, "Mock 模式：GPT2 自回归语义编码采样..."),
        (0.80, f"Mock 模式：S2Mel 流匹配 ({req.diffusion_steps} 步) + BigVGAN 合成..."),
        (0.94, "Mock 模式：音频母带处理与时间轴字幕封装..."),
    ]
    for p, desc in stages:
        progress_cb(p, desc)
        time.sleep(0.24)

    sr = 22050
    pause_bonus = max(0, len(est_segs) - 1) * (req.interval_silence_ms / 1000.0)
    est_seconds = max(1.6, min(10.0, len(req.text) * 0.14 * req.duration_factor + pause_bonus))
    total_samples = int(sr * est_seconds)
    freqs = (261.63, 329.63, 392.00)
    buf = bytearray(total_samples * 2)
    for i in range(total_samples):
        t = i / sr
        env = min(1.0, t / 0.08) * min(1.0, (est_seconds - t) / 0.25)
        pulse = 0.65 + 0.35 * math.sin(2 * math.pi * 2.2 * t)
        val = sum(math.sin(2 * math.pi * f * t) for f in freqs) / len(freqs)
        sample = int(max(-1.0, min(1.0, val * env * pulse * 0.30)) * 32767)
        struct.pack_into("<h", buf, i * 2, sample)

    processed_pcm = _postprocess_pcm16(
        bytes(buf),
        sample_rate=sr,
        trim_silence=req.trim_silence,
        tail_fade_ms=req.tail_fade_ms,
    )
    filename, dest, actual_fmt, final_dur = _encode_audio_file(
        processed_pcm,
        sr,
        req.output_format,
        req.loudness_norm,
        storage,
        prefix=f"indextts25_{req.emotion_mode}",
    )
    subtitle, srt, vtt, timeline = _build_subtitles(
        req.text,
        final_dur,
        req.max_text_tokens_per_segment,
    )
    infer_elapsed = max(0.01, time.perf_counter() - t0)
    return {
        "audio_url": f"/api/v1/outputs/{filename}",
        "download_url": f"/api/v1/outputs/{filename}?download=true",
        "filename": filename,
        "format": actual_fmt,
        "sample_rate": sr,
        "duration_sec": round(final_dur, 2),
        "size_bytes": dest.stat().st_size,
        "seed": actual_seed,
        "language": req.language,
        "emotion_mode": req.emotion_mode,
        "effective_emo_vector": effective_emo_vec,
        "segments_count": len(est_segs),
        "rtf": round(infer_elapsed / max(0.1, final_dur), 3),
        "speaker_audio_ref": req.speaker_audio,
        "subtitle": subtitle,
        "srt": srt,
        "vtt": vtt,
        "timeline": timeline,
        "subtitle_timing": "estimated",
        "mock": True,
    }


def execute_indextts_task(
    params: Dict[str, Any],
    storage: MediaStorage,
    settings: AppSettings,
    progress_cb: ProgressCallback,
) -> Dict[str, Any]:
    req = IndexTTSGenerateRequest.model_validate(params)
    spk_path = storage.resolve_input_ref(req.speaker_audio)

    emo_audio_path: Optional[Path] = None
    emo_vec: Optional[List[float]] = None
    use_emo_text = False
    emo_text: Optional[str] = None

    if req.emotion_mode == "vector" and req.emotion_vector is not None:
        raw_list = req.emotion_vector.to_ordered_list()
        emo_vec = compute_effective_emo_vector(
            raw_list,
            apply_bias=req.apply_emo_bias,
            cap_sum=req.normalize_emo_vector,
        )
    elif req.emotion_mode == "reference" and req.emotion_audio:
        emo_audio_path = storage.resolve_input_ref(req.emotion_audio)
    elif req.emotion_mode == "text":
        use_emo_text = True
        cleaned_emo_text = (req.emotion_text or "").strip()
        # Passing None causes IndexTTS2 to automatically infer emotion from `req.text`
        emo_text = None if (req.auto_emotion_from_text or not cleaned_emo_text) else cleaned_emo_text

    actual_seed = req.seed if req.seed > 0 else random.randint(1, 2147483647)

    if settings.mock_inference:
        return _run_mock_synthesis(req, actual_seed, emo_vec, storage, progress_cb)

    import numpy as np  # type: ignore
    import torch  # type: ignore

    def _gr_progress_bridge(value: float, desc: str = "") -> None:
        mapped = 0.10 + 0.80 * max(0.0, min(1.0, float(value)))
        progress_cb(mapped, str(desc or "正在合成语音..."))

    with ENGINE_MANAGER.use_engine(
        use_bf16=req.use_bf16,
        use_qwen_emo=use_emo_text,
        use_cuda_kernel=req.use_cuda_kernel,
        use_torch_compile=req.use_torch_compile,
        progress_cb=progress_cb,
        auto_free_memory=req.auto_free_memory,
    ) as tts:
        # Loading weights can consume RNG state. Seed after loading so a take
        # restored from history behaves the same with a warm or cold engine.
        random.seed(actual_seed)
        np.random.seed(actual_seed % (2**32 - 1))
        torch.manual_seed(actual_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(actual_seed)
        t0 = time.perf_counter()
        tts.gr_progress = _gr_progress_bridge
        try:
            with _override_indextts_runtime_knobs(
                tts,
                max_ref_seconds=req.max_ref_seconds,
                diffusion_steps=req.diffusion_steps,
                inference_cfg_rate=req.inference_cfg_rate,
            ):
                result = tts.infer(
                    spk_audio_prompt=str(spk_path),
                    text=req.text,
                    output_path=None,
                    lang=req.language,
                    emo_audio_prompt=str(emo_audio_path) if emo_audio_path else None,
                    emo_alpha=float(req.emo_alpha),
                    emo_vector=emo_vec,
                    use_emo_text=use_emo_text,
                    emo_text=emo_text,
                    use_random=bool(req.use_random),
                    interval_silence=int(req.interval_silence_ms),
                    max_text_tokens_per_segment=int(req.max_text_tokens_per_segment),
                    duration_factor=float(req.duration_factor),
                    text_normalization=bool(req.text_normalization),
                    do_sample=bool(req.do_sample),
                    temperature=float(req.temperature),
                    top_p=float(req.top_p),
                    top_k=int(req.top_k),
                    repetition_penalty=float(req.repetition_penalty),
                    length_penalty=float(req.length_penalty),
                    num_beams=int(req.num_beams),
                    max_mel_tokens=int(req.max_mel_tokens),
                )
            infer_elapsed = max(0.01, time.perf_counter() - t0)
        finally:
            tts.gr_progress = None

    if result is None:
        raise RuntimeError("IndexTTS-2.5 推理返回空结果，请检查输入文本或参考音频是否有效。")

    sr, wav = result
    sr = int(sr)
    wav_arr = np.asarray(wav)
    if wav_arr.ndim == 2:
        wav_arr = wav_arr[:, 0]
    if wav_arr.dtype != np.int16:
        wav_arr = np.clip(wav_arr * 32767.0, -32768, 32767).astype(np.int16)

    progress_cb(0.94, "正在执行母带处理并编码写入音频文件...")
    processed_pcm = _postprocess_pcm16(
        wav_arr.tobytes(),
        sample_rate=sr,
        trim_silence=req.trim_silence,
        tail_fade_ms=req.tail_fade_ms,
    )

    filename, dest, actual_fmt, final_dur = _encode_audio_file(
        processed_pcm,
        sr,
        req.output_format,
        req.loudness_norm,
        storage,
        prefix=f"indextts25_{req.emotion_mode}",
    )
    subtitle, srt, vtt, timeline = _build_subtitles(
        req.text,
        final_dur,
        req.max_text_tokens_per_segment,
    )
    est_segs = _estimate_segments(req.text, req.max_text_tokens_per_segment)

    return {
        "audio_url": f"/api/v1/outputs/{filename}",
        "download_url": f"/api/v1/outputs/{filename}?download=true",
        "filename": filename,
        "format": actual_fmt,
        "sample_rate": sr,
        "duration_sec": round(final_dur, 2),
        "size_bytes": dest.stat().st_size,
        "seed": actual_seed,
        "language": req.language,
        "emotion_mode": req.emotion_mode,
        "effective_emo_vector": emo_vec,
        "segments_count": len(est_segs),
        "rtf": round(infer_elapsed / max(0.1, final_dur), 3),
        "speaker_audio_ref": req.speaker_audio,
        "subtitle": subtitle,
        "srt": srt,
        "vtt": vtt,
        "timeline": timeline,
        "subtitle_timing": "estimated",
        "mock": False,
    }

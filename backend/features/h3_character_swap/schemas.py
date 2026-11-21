"""Pydantic schemas, canvas geometry, prompt builder, and window planner for H3 Character Swap."""
from typing import Dict, List, Literal, Tuple
from pydantic import BaseModel, Field, field_validator, model_validator

NATIVE_FPS = 24
DEFAULT_SWAP_SIGMAS = "1.0, 0.972973, 0.923077, 0.8, 0.571429, 0.333333, 0.0"
DEFAULT_SWAP_STEPS = 8
DEFAULT_SWAP_SCHEDULER = "normal"
DEFAULT_SHIFT_VIDEO = 12.0
DEFAULT_SHIFT_AUDIO = 3.0
DEFAULT_MASK_EXPANSION_PX = 64
MAX_CHARACTERS = 9
MAX_GUIDE_FRAMES = 4
MIN_WINDOW_FRAMES = 22
MAX_WINDOW_FRAMES = 345
DEFAULT_WINDOW_FRAMES = 226
HISTORY_OVERLAP_FRAMES = 5
MAX_CLIP_DURATION_SEC = 60.0

SwapMode = Literal["single", "multi"]
ResolutionTier = Literal["480p", "736p"]
SamplerChoice = Literal["er_sde", "euler", "lcm"]
SchedulerChoice = Literal["normal", "simple", "beta", "sgm_uniform"]
MaskSelection = Literal["largest", "leftmost", "rightmost", "index"]
RefImageSize = Literal["match", "max"]
VideoOutputFormat = Literal["mp4", "webm", "mkv"]


def snap32(value: float, minimum: int = 32) -> int:
    """Round pixel dimension to the nearest 32-pixel multiple (at least `minimum`)."""
    snapped = int(round(float(value) / 32.0) * 32)
    return max(minimum, snapped)


def compute_swap_dimensions(
    src_w: int,
    src_h: int,
    resolution_tier: ResolutionTier,
    preserve_aspect: bool = True,
) -> Tuple[int, int]:
    """Compute 32-pixel-aligned canvas dimensions for H3 Character Swap."""
    sw = max(2, int(src_w))
    sh = max(2, int(src_h))
    short_edge = 736 if resolution_tier == "736p" else 480
    landscape = sw >= sh

    if not preserve_aspect:
        long_edge = 1280 if resolution_tier == "736p" else 832
        return (long_edge, short_edge) if landscape else (short_edge, long_edge)

    raw_ratio = max(sw, sh) / max(1, min(sw, sh))
    clamped_ratio = max(1.0, min(1.85, raw_ratio))
    long_edge = snap32(short_edge * clamped_ratio, minimum=short_edge)
    return (long_edge, short_edge) if landscape else (short_edge, long_edge)


def next_valid_frame_count(raw_frames: int) -> int:
    """Return the smallest valid 17n+5 frame count >= max(22, raw_frames), capped at 345."""
    target = max(MIN_WINDOW_FRAMES, min(MAX_WINDOW_FRAMES, int(raw_frames)))
    rem = (target - 5) % 17
    if rem != 0:
        target += 17 - rem
    return min(MAX_WINDOW_FRAMES, max(MIN_WINDOW_FRAMES, target))


def plan_swap_windows(
    total_frames: int,
    max_window_frames: int = DEFAULT_WINDOW_FRAMES,
    overlap_frames: int = HISTORY_OVERLAP_FRAMES,
) -> List[Dict[str, int]]:
    """Plan single or overlapping continuation windows for a clip."""
    total = max(1, int(total_frames))
    max_win = max(56, min(MAX_WINDOW_FRAMES, int(max_window_frames)))
    overlap = max(0, min(max_win - 1, int(overlap_frames)))

    if total <= max_win:
        return [
            {
                "index": 0,
                "source_start": 0,
                "source_frames": total,
                "history_frames": 0,
                "padded_frames": next_valid_frame_count(total),
            }
        ]

    windows: List[Dict[str, int]] = [
        {
            "index": 0,
            "source_start": 0,
            "source_frames": max_win,
            "history_frames": 0,
            "padded_frames": next_valid_frame_count(max_win),
        }
    ]
    cursor = max_win
    step_capacity = max(1, max_win - overlap)
    index = 1
    while cursor < total:
        chunk_frames = min(step_capacity, total - cursor)
        windows.append(
            {
                "index": index,
                "source_start": cursor,
                "source_frames": chunk_frames,
                "history_frames": overlap,
                "padded_frames": next_valid_frame_count(overlap + chunk_frames),
            }
        )
        cursor += chunk_frames
        index += 1
    return windows


class CharacterSlot(BaseModel):
    image: str = Field(..., min_length=1, description="Uploaded file_id or storage ref for <Picture N>")
    name: str = Field(default="", max_length=120, description="Optional character name")
    target_description: str = Field(
        default="",
        max_length=500,
        description="Which person in <Video 1> this character replaces (e.g., left dancer in black jacket)",
    )
    appearance_description: str = Field(
        default="",
        max_length=1000,
        description="Optional details about face, hair, outfit, or accessories from <Picture N>",
    )

    @field_validator("image")
    @classmethod
    def _clean_image(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("角色参考图片不能为空。")
        return clean

    @field_validator("name", "target_description", "appearance_description")
    @classmethod
    def _strip_optional_text(cls, value: str) -> str:
        return value.strip()


class GuideFrameSlot(BaseModel):
    image: str = Field(..., min_length=1, description="Edited source frame used as an anchor guide")
    frame_index: int = Field(default=0, ge=0, le=20000, description="Target 24fps frame index inside clip")

    @field_validator("image")
    @classmethod
    def _clean_guide_image(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("引导关键帧图片不能为空。")
        return clean


def _format_character_phrase(pic_ref: str, name: str, appearance: str) -> str:
    details = ", ".join(part for part in (name, appearance) if part)
    return f"{details} in {pic_ref}" if details else f"the character in {pic_ref}"


def build_swap_prompt(
    mode: SwapMode,
    characters: List[CharacterSlot],
    user_prompt: str,
    keep_audio: bool = True,
) -> str:
    """Return user's explicit <Video 1>/<Picture 1> prompt verbatim, or build natural H3 swap prompt."""
    cleaned_user = (user_prompt or "").strip()
    lower = cleaned_user.lower()
    if cleaned_user and "<video 1>" in lower and "<picture 1>" in lower:
        return cleaned_user

    parts: List[str] = []
    if mode == "single":
        pic_refs = (
            "<Picture 1>"
            if len(characters) == 1
            else " and ".join(f"<Picture {i}>" for i in range(1, len(characters) + 1))
        )
        primary = characters[0]
        target = primary.target_description or "the selected person"
        char_phrase = _format_character_phrase(
            pic_refs, primary.name, primary.appearance_description
        )
        parts.append(
            f"Replace {target} in <Video 1> with {char_phrase}. "
            "Match the reference face, hairstyle and complete outfit consistently from the first frame. "
            "Match the reference garment shapes, layers, colors, hemline, exposed skin, legwear and shoes. "
            "Follow the source person's pose, gaze, expressions, motion, position, scale and timing. "
            "Preserve the scene, camera movement, lighting and other people."
        )
    else:
        for idx, slot in enumerate(characters, 1):
            target = slot.target_description or (
                f"person {idx}" if len(characters) > 1 else "the selected person"
            )
            char_phrase = _format_character_phrase(
                f"<Picture {idx}>", slot.name, slot.appearance_description
            )
            parts.append(f"Replace {target} in <Video 1> with {char_phrase}.")
        parts.append(
            "Match each reference character's face, hairstyle and complete outfit consistently from the first frame. "
            "Keep each replacement matched to its source person; leave all other people unchanged. "
            "Follow the source motion, pose, gaze, expressions, camera movement, lighting and background."
        )

    if keep_audio:
        parts.append("Follow <Audio 1> for speech and performance timing.")
    if cleaned_user:
        parts.append(cleaned_user)
    return " ".join(parts)


build_remake_prompt = build_swap_prompt


def parse_sigma_schedule(raw: str) -> List[float]:
    tokens = [tok for tok in (raw or "").replace(",", " ").split() if tok]
    if len(tokens) < 2:
        raise ValueError("Sigma 时间表至少需要 2 个数值（且末位必须为 0.0）。")
    try:
        values = [float(tok) for tok in tokens]
    except ValueError as exc:
        raise ValueError("Sigma 时间表格式无效，请使用逗号分隔的数字。") from exc
    if any(v < 0.0 or v > 1.0 for v in values):
        raise ValueError("Sigma 数值必须在 0.0 到 1.0 之间。")
    if values[-1] != 0.0:
        raise ValueError("Sigma 时间表最后一项必须为 0.0。")
    for prev, nxt in zip(values, values[1:]):
        if prev < nxt:
            raise ValueError("Sigma 时间表必须单调递减。")
    return values


class H3CharacterSwapGenerateRequest(BaseModel):
    mode: SwapMode = "single"
    source_video: str = Field(..., min_length=1, description="Uploaded source performance video file_id")
    characters: List[CharacterSlot] = Field(..., min_length=1, max_length=MAX_CHARACTERS)
    prompt: str = Field(default="", max_length=8000)
    guide_frames: List[GuideFrameSlot] = Field(default_factory=list, max_length=MAX_GUIDE_FRAMES)

    resolution_tier: ResolutionTier = "480p"
    preserve_aspect: bool = True
    start_time_sec: float = Field(default=0.0, ge=0.0, le=3600.0)
    duration_sec: float = Field(default=0.0, ge=0.0, le=MAX_CLIP_DURATION_SEC)
    keep_audio: bool = True

    window_frames: int = Field(default=DEFAULT_WINDOW_FRAMES, ge=56, le=MAX_WINDOW_FRAMES)
    keyframe_until: float = Field(default=0.9, ge=0.0, le=1.0)
    sigmas: str = Field(default=DEFAULT_SWAP_SIGMAS, max_length=256)
    sampler_name: SamplerChoice = "er_sde"
    steps: int = Field(default=DEFAULT_SWAP_STEPS, ge=4, le=40)
    scheduler: SchedulerChoice = DEFAULT_SWAP_SCHEDULER
    shift_video: float = Field(default=DEFAULT_SHIFT_VIDEO, ge=0.5, le=30.0)
    shift_audio: float = Field(default=DEFAULT_SHIFT_AUDIO, ge=0.5, le=20.0)
    turbo_lora_strength: float = Field(default=1.0, ge=0.0, le=2.0)
    pika_lora_strength: float = Field(default=1.0, ge=0.0, le=2.0)
    swap_lora_strength: float = Field(default=1.0, ge=0.0, le=2.0)
    enable_edit_mask: bool = True
    mask_subject_prompt: str = Field(default="person", max_length=120)
    mask_selection: MaskSelection = "largest"
    mask_index: int = Field(default=0, ge=0, le=16)
    mask_expansion_px: int = Field(default=DEFAULT_MASK_EXPANSION_PX, ge=0, le=256)
    ref_image_size: RefImageSize = "match"
    seed: int = Field(default=0, ge=0, le=0xFFFFFFFFFFFFFFFF)
    output_format: VideoOutputFormat = "mp4"

    @field_validator("source_video")
    @classmethod
    def _clean_source_video(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("请先上传待替换的原视频。")
        return clean

    @field_validator("window_frames")
    @classmethod
    def _validate_window_frames(cls, value: int) -> int:
        if (value - 5) % 17 != 0:
            raise ValueError("window_frames 必须满足 17n + 5（例如 124、226、345）。")
        return value

    @field_validator("sigmas")
    @classmethod
    def _validate_sigmas(cls, value: str) -> str:
        parse_sigma_schedule(value)
        return value.strip()

    @model_validator(mode="after")
    def _validate_relationships(self) -> "H3CharacterSwapGenerateRequest":
        if len(self.characters) < 1 or len(self.characters) > MAX_CHARACTERS:
            raise ValueError(f"角色参考图数量需在 1 到 {MAX_CHARACTERS} 张之间。")
        if len(self.guide_frames) > MAX_GUIDE_FRAMES:
            raise ValueError(f"可选关键帧引导最多支持 {MAX_GUIDE_FRAMES} 帧。")
        return self


class H3CharacterSwapResult(BaseModel):
    video_url: str
    filename: str
    format: VideoOutputFormat
    width: int
    height: int
    fps: int
    frame_count: int
    duration_sec: float
    has_audio: bool
    size_bytes: int
    seed: int
    mode: SwapMode
    character_count: int
    window_count: int
    resolution_tier: ResolutionTier
    source_video_ref: str
    input_width: int
    input_height: int
    input_fps: float
    input_start_time: float
    effective_prompt: str
    elapsed_sec: float
    mock: bool = False

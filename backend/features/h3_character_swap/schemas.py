"""Pydantic schemas, canvas geometry, prompt builder, and window planner for H3 Character Swap."""
from typing import Dict, List, Literal, Tuple
from pydantic import BaseModel, Field, field_validator, model_validator

NATIVE_FPS = 24
DEFAULT_SWAP_SIGMAS = "1.0, 0.990476, 0.965243, 0.923077, 0.8, 0.631579, 0.0"
MAX_CHARACTERS = 9
MAX_GUIDE_FRAMES = 4
MIN_WINDOW_FRAMES = 22
MAX_WINDOW_FRAMES = 345
DEFAULT_WINDOW_FRAMES = 226
HISTORY_OVERLAP_FRAMES = 18
MAX_CLIP_DURATION_SEC = 60.0

SwapMode = Literal["single", "multi"]
ResolutionTier = Literal["480p", "736p"]
SamplerChoice = Literal["euler", "er_sde", "lcm"]
VideoOutputFormat = Literal["mp4", "webm", "mkv"]

_PROMPT_SECTIONS = (
    "subject_definitions:",
    "summary:",
    "retention_analysis:",
    "detailed_description:",
    "overall_soundscape:",
    "non_diegetic_music:",
)


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
    """Compute 32-pixel-aligned canvas dimensions for Viggle Remake Swap."""
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
    """Plan single or 18-frame overlapping continuation windows for a clip."""
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


def build_remake_prompt(
    mode: SwapMode,
    characters: List[CharacterSlot],
    user_prompt: str,
    keep_audio: bool = True,
) -> str:
    """Return user's 6-section prompt verbatim, or expand structured Viggle Remake sections."""
    cleaned_user = (user_prompt or "").strip()
    lower = cleaned_user.lower()
    if cleaned_user and all(section in lower for section in _PROMPT_SECTIONS):
        return cleaned_user

    pic_count = len(characters)
    if pic_count == 1:
        pic_intro = "<Picture 1> shows the target character appearance."
    else:
        pic_labels = ", ".join(f"<Picture {i}>" for i in range(1, pic_count + 1))
        pic_intro = f"{pic_labels} show the target replacement character references."

    subject_lines = [
        f"<Video 1> is the source video for editing: keep its motion, pose, camera framing, lighting and background.",
        pic_intro,
    ]
    retention_subjects: List[str] = []
    summary_swaps: List[str] = []

    if mode == "single" and pic_count > 1:
        pic_refs = " and ".join(f"<Picture {i}>" for i in range(1, pic_count + 1))
        primary = characters[0]
        subj_name = primary.name or "the target character"
        target = primary.target_description or "the main person in <Video 1>"
        appearance = primary.appearance_description or f"the face, hairstyle, build and complete outfit in {pic_refs}"
        subject_lines.append(
            f"<Subject 1> is {subj_name} in {pic_refs}: {appearance}. "
            f"<Subject 1> replaces {target} in <Video 1>."
        )
        summary_swaps.append(f"{target} becomes <Subject 1>")
        retention_subjects.append(
            f"<Subject 1>: fully_preserved - {appearance} stays identical across every frame."
        )
    else:
        for idx, slot in enumerate(characters, 1):
            subj_name = slot.name or f"Character {idx}"
            target = slot.target_description or (
                "the primary person in <Video 1>" if idx == 1 else f"person {idx} in <Video 1>"
            )
            appearance = (
                slot.appearance_description
                or f"the exact face, hairstyle, outfit and proportions shown in <Picture {idx}>"
            )
            subject_lines.append(
                f"<Subject {idx}> is {subj_name} in <Picture {idx}>: {appearance}. "
                f"<Subject {idx}> replaces {target} in <Video 1> cleanly without swapping into other people."
            )
            summary_swaps.append(f"{target} becomes <Subject {idx}>")
            retention_subjects.append(
                f"<Subject {idx}> (<Picture {idx}>): fully_preserved - {appearance} stays consistent in every frame."
            )

    swap_clause = "; ".join(summary_swaps)
    extra_detail = cleaned_user or (
        "Preserve natural lighting, sharp textures, facial expressions, gaze, hand gestures and camera movement."
    )

    retention_pics = "\n".join(
        f"<Picture {idx}>: reference - exact character identity, face, hair and garments are taken from <Picture {idx}>."
        for idx in range(1, pic_count + 1)
    )
    soundscape = (
        "The original <Video 1> soundtrack, voice timing and ambient audio continue seamlessly."
        if keep_audio
        else "Silent output video preserving clean visual pacing."
    )

    return "\n".join(
        [
            "subject_definitions:",
            *subject_lines,
            "",
            "summary:",
            f"[video editing + character replacement] The target video reproduces <Video 1> where {swap_clause}. "
            "All unchanged people, scene geometry, camera motion and lighting remain identical to <Video 1>.",
            "",
            "retention_analysis:",
            "<Video 1> (source video editing): fully_preserved - shots, cuts, camera movement, background, "
            "lighting, pose and motion timing are copied accurately frame by frame.",
            retention_pics,
            *retention_subjects,
            "",
            "detailed_description:",
            "The target video maintains natural clear illumination, sharp details and the camera look of <Video 1>. "
            f"{extra_detail}",
            "",
            "overall_soundscape:",
            soundscape,
            "",
            "non_diegetic_music:",
            "N/A",
        ]
    )


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
    sampler_name: SamplerChoice = "euler"
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

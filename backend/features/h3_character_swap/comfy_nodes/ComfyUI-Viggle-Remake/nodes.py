# SPDX-License-Identifier: Apache-2.0
"""Viggle Remake custom nodes for ComfyUI's built-in MiniMax-H3 support.

Derived from Viggle/Viggle-Remake (commit 7e5be143702dd53b9154482de673b8519ed2d4d6)
and akatz-labs/h3-character-swap-tool worker runtime nodes under Apache-2.0.
"""
from __future__ import annotations

import os
from typing import List

FPS = 24
AUDIO_SR = 32000
AUDIO_LATENT_FPS = 40
FF_ROWS = 16384


def stamps(nf: int) -> List[float]:
    """Return 2 fps paired block mean timestamps (seconds) for an `nf`-frame clip."""
    idx: List[int] = []
    cursor = 0.0
    while round(cursor) < nf:
        if not idx or round(cursor) > idx[-1]:
            idx.append(round(cursor))
        cursor += FPS / 2.0
    t = [i / 2.0 for i in range(len(idx))]
    t += t[-1:] * (len(t) % 2)
    return [(t[i] + t[i + 1]) / 2.0 for i in range(0, len(t), 2)]


def _ensure_mlp_row_chunking() -> None:
    """Optionally bound H3 MLP activation memory via chunked forward passes."""
    raw_rows = os.environ.get("H3_MLP_CHUNK_ROWS", "").strip()
    row_limit = int(raw_rows) if raw_rows.isdigit() and int(raw_rows) > 0 else FF_ROWS
    try:
        import torch
        import comfy.ldm.minimax.model as h3_model
    except ImportError:
        return
    mlp_cls = getattr(h3_model, "MLP", None)
    if mlp_cls is None or getattr(mlp_cls.forward, "_viggle_remake_chunked", False):
        return
    orig_forward = mlp_cls.forward

    def chunked_forward(self, x):
        if x.shape[-2] <= row_limit:
            return orig_forward(self, x)
        out = torch.empty_like(x)
        for start in range(0, x.shape[-2], row_limit):
            out[..., start : start + row_limit, :] = orig_forward(
                self, x[..., start : start + row_limit, :]
            )
        return out

    chunked_forward._viggle_remake_chunked = True  # type: ignore[attr-defined]
    mlp_cls.forward = chunked_forward


def _lanczos(image, width: int, height: int):
    import comfy.utils

    return (
        comfy.utils.common_upscale(
            image.movedim(-1, 1), width, height, "lanczos", "disabled"
        )
        .movedim(1, -1)
    )


def _cover(image, width: int, height: int):
    h, w = image.shape[1], image.shape[2]
    scale = max(width / w, height / h)
    sw, sh = max(width, round(w * scale)), max(height, round(h * scale))
    left, top = (sw - width) // 2, (sh - height) // 2
    return _lanczos(image, sw, sh)[:, top : top + height, left : left + width]


class H3RemakeConditioning:
    """Build MiniMax-H3 Viggle Remake text/visual conditioning and clean audio target latent."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "audio_vae": ("VAE",),
                "source": (
                    "IMAGE",
                    {
                        "tooltip": "Source video frames at 24 fps aligned to 32-pixel canvas.",
                    },
                ),
                "prompt": (
                    "STRING",
                    {"multiline": True, "tooltip": "Six-section Viggle Remake prompt used verbatim."},
                ),
                "frames": ("INT", {"default": 124, "min": 5, "max": 396, "step": 17}),
            },
            "optional": {
                "audio": ("AUDIO",),
                "ref_1": ("IMAGE",),
                "ref_2": ("IMAGE",),
                "ref_3": ("IMAGE",),
                "ref_4": ("IMAGE",),
                "ref_5": ("IMAGE",),
                "ref_6": ("IMAGE",),
                "ref_7": ("IMAGE",),
                "ref_8": ("IMAGE",),
                "ref_9": ("IMAGE",),
                "pins": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("CONDITIONING", "LATENT")
    RETURN_NAMES = ("positive", "latent")
    FUNCTION = "run"
    CATEGORY = "Viggle Remake"

    def run(
        self,
        clip,
        vae,
        audio_vae,
        source,
        prompt,
        frames,
        audio=None,
        pins="",
        **references,
    ):
        import torch
        import comfy.audio
        import comfy.nested_tensor
        import node_helpers

        _ensure_mlp_row_chunking()
        nf = int(frames)
        if nf < 5 or (nf - 5) % 17 != 0:
            raise ValueError(f"frames must be 17n+5, got {nf}")

        refs = [
            references[f"ref_{i}"][:1, ..., :3]
            for i in range(1, 10)
            if references.get(f"ref_{i}") is not None
        ]
        pin_tokens = [p for p in str(pins or "").replace(",", " ").split() if p]
        pin_indices = [int(p) for p in pin_tokens]
        if len(pin_indices) not in (0, len(refs)):
            raise ValueError(
                f"pins must provide one frame index per reference or be empty ({len(pin_indices)} vs {len(refs)})"
            )
        if any(not (0 <= p < nf) for p in pin_indices):
            raise ValueError(f"pins must fall in [0, {nf})")

        source = source[:nf, ..., :3]
        h, w = source.shape[1], source.shape[2]
        if h % 32 != 0 or w % 32 != 0 or source.shape[0] < nf:
            raise ValueError(
                f"Source must match padded 32-pixel canvas with at least {nf} frames (got {tuple(source.shape)})"
            )
        se = min(h, w)

        segments = [
            "<Video 1>: ",
            *["<%.1f seconds>" % s for s in stamps(nf)],
            *["<Picture %d>: " % (i + 1) for i in range(len(refs))],
            prompt,
        ]
        tokens = {
            "qwen3vl_32b": [
                [t for seg in segments for t in clip.tokenize(seg)["qwen3vl_32b"][0]]
            ]
        }
        positive = clip.encode_from_tokens_scheduled(tokens)

        z = vae.encode(source)
        blocks = [
            {
                "kind": "video",
                "latent_t": z.shape[2],
                "latent_h": h // 16,
                "latent_w": w // 16,
                "ref_audio_t": 0,
                "latent": z,
                "audio_latent": None,
            }
        ]
        for ref in refs:
            rh, rw = ref.shape[1], ref.shape[2]
            th = max(32, round(rh * se / min(rh, rw) / 32) * 32)
            tw = max(32, round(rw * se / min(rh, rw) / 32) * 32)
            resized = ref if (rh, rw) == (th, tw) else _lanczos(ref, tw, th)
            blocks.append(
                {
                    "kind": "image",
                    "latent_h": th // 16,
                    "latent_w": tw // 16,
                    "latent": vae.encode(resized),
                }
            )

        cond_values = {"minimax_refs": blocks}
        if pin_indices:
            keyframes = []
            for idx, (ref, frame_idx) in enumerate(zip(refs, pin_indices)):
                kf = ref
                if (kf.shape[1], kf.shape[2]) != (h, w):
                    kf = _lanczos(kf, w, h) if idx == 0 else _cover(kf, w, h)
                keyframes.append({"resolved_frame_index": frame_idx, "latent": vae.encode(kf)})
            cond_values["minimax_keyframes"] = keyframes

        positive = node_helpers.conditioning_set_values(positive, cond_values)

        n = round((nf + 1) / FPS * AUDIO_SR)
        wav = torch.zeros(2, n)
        if audio is not None:
            wav, sr = audio["waveform"][0].float(), audio["sample_rate"]
            wav = wav.repeat(2, 1) if wav.shape[0] == 1 else wav[:2]
            wav = wav[:, : round(nf / FPS * sr)]
            wav = comfy.audio.resample(wav, sr, AUDIO_SR) if sr != AUDIO_SR else wav
        wav = torch.nn.functional.pad(wav, (0, max(0, n - wav.shape[1])))[:, :n]
        wav = torch.nn.functional.pad(wav, (0, -n % 800))
        za = audio_vae.encode(wav[None].movedim(1, -1))[
            ..., : round(nf / FPS * AUDIO_LATENT_FPS)
        ]

        video = torch.zeros(1, 24, (nf - 5) // 17 * 5 + 2, h // 16, w // 16)
        latent = {
            "samples": comfy.nested_tensor.NestedTensor((video, za)),
            "noise_mask": comfy.nested_tensor.NestedTensor(
                (torch.ones_like(video), torch.zeros_like(za))
            ),
        }
        return (positive, latent)


class H3RemakeKeyframeUntil:
    """Release pinned keyframes below `keyframe_until` sigma so motion stays fluid."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "keyframe_until": (
                    "FLOAT",
                    {"default": 0.9, "min": 0.0, "max": 1.0, "step": 0.01},
                ),
            }
        }

    RETURN_TYPES = ("MODEL",)
    FUNCTION = "run"
    CATEGORY = "Viggle Remake"

    def run(self, model, keyframe_until):
        import comfy.patcher_extension

        def release(
            executor,
            x,
            timestep,
            context,
            transformer_options,
            minimax_payload=None,
            **kwargs,
        ):
            p = minimax_payload or {}
            if p.get("keyframes") and float(timestep.flatten()[0]) / 1000.0 < keyframe_until:
                refs = p.get("refs") or []
                minimax_payload = dict(
                    p,
                    keyframes=None,
                    layout=None,
                    cond_video_latents=[r["latent"] for r in refs if "latent" in r],
                    cond_audio_latents=[
                        r["audio_latent"]
                        for r in refs
                        if r.get("audio_latent") is not None
                    ],
                )
            return executor(
                x,
                timestep,
                context,
                transformer_options,
                minimax_payload=minimax_payload,
                **kwargs,
            )

        cloned = model.clone()
        cloned.add_wrapper_with_key(
            comfy.patcher_extension.WrappersMP.DIFFUSION_MODEL,
            "viggle_remake_keyframe_until",
            release,
        )
        return (cloned,)


class _RemakeNoiseGenerator:
    def __init__(self, seed: int, skip_shapes):
        self.seed = seed
        self.skip_shapes = skip_shapes

    def generate_noise(self, input_latent):
        import torch
        import comfy.nested_tensor

        gen = torch.Generator().manual_seed(self.seed)
        for shape in self.skip_shapes:
            torch.randn(shape, generator=gen)
        return comfy.nested_tensor.NestedTensor(
            [torch.randn(t.shape, generator=gen) for t in input_latent["samples"].unbind()]
        )


class H3RemakeNoise:
    """Draw deterministic starting noise aligned with reference/keyframe latent shapes."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "positive": ("CONDITIONING",),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFFFFFFFFFF,
                        "control_after_generate": True,
                    },
                ),
            }
        }

    RETURN_TYPES = ("NOISE",)
    FUNCTION = "run"
    CATEGORY = "Viggle Remake"

    def run(self, positive, seed):
        cond_meta = positive[0][1]
        skip_shapes = [
            b["latent"].shape
            for b in cond_meta.get("minimax_refs", [])
            + cond_meta.get("minimax_keyframes", [])
            if "latent" in b
        ]
        return (_RemakeNoiseGenerator(int(seed), skip_shapes),)


class H3RemakePrefix:
    """Pin clean frames from the previous take at the opening of a continuation window."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "vae": ("VAE",),
                "latent": ("LATENT",),
                "prefix": ("IMAGE",),
                "prefix_frames": ("INT", {"default": 17, "min": 17, "max": 323, "step": 17}),
                "prefix_at": ("INT", {"default": -1, "min": -1, "max": 100000}),
            }
        }

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "run"
    CATEGORY = "Viggle Remake"

    def run(self, vae, latent, prefix, prefix_frames, prefix_at):
        import torch
        import comfy.nested_tensor

        k = int(prefix_frames)
        at = len(prefix) - k if prefix_at < 0 else int(prefix_at)
        px = prefix[at : at + k, ..., :3]
        video, audio = latent["samples"].unbind()
        vmask, amask = latent["noise_mask"].unbind()
        n = k // 17 * 5
        if k % 17 != 0 or n >= video.shape[2]:
            raise ValueError(f"prefix_frames must be a multiple of 17 shorter than render, got {k}")
        expected = (k, video.shape[3] * 16, video.shape[4] * 16)
        if tuple(px.shape[:3]) != expected:
            raise ValueError(f"prefix frames must have shape {expected}, got {tuple(px.shape)}")
        clean = vae.encode(torch.cat([px, px[-1:].repeat(5, 1, 1, 1)]))[:, :, :n]
        video, vmask = video.clone(), vmask.clone()
        video[:, :, :n] = clean.to(video)
        vmask[:, :, :n] = 0
        return (
            {
                **latent,
                "samples": comfy.nested_tensor.NestedTensor((video, audio)),
                "noise_mask": comfy.nested_tensor.NestedTensor((vmask, amask)),
            },
        )


class H3RemakeHistory:
    """Apply 18-frame continuation history (17 clean prefix frames + 1 boundary keyframe)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "positive": ("CONDITIONING",),
                "latent": ("LATENT",),
                "vae": ("VAE",),
                "frames": ("IMAGE",),
                "history_frames": ("INT", {"default": 18, "min": 1, "max": 18}),
            }
        }

    RETURN_TYPES = ("CONDITIONING", "LATENT")
    FUNCTION = "run"
    CATEGORY = "Viggle Remake"

    def run(self, positive, latent, vae, frames, history_frames):
        import node_helpers

        hf = int(history_frames)
        if hf not in (1, 18) or len(frames) < hf:
            raise ValueError(
                f"Continuation requires history_frames in (1, 18) with enough frames (got {hf}, len={len(frames)})"
            )
        selected = frames[:hf]
        if hf == 18:
            (latent,) = H3RemakePrefix().run(vae, latent, selected, 17, 0)
        boundary = {
            "resolved_frame_index": hf - 1,
            "latent": vae.encode(selected[-1:, ..., :3]),
        }
        positive = node_helpers.conditioning_set_values(
            positive,
            {
                "minimax_keyframes": list(positive[0][1].get("minimax_keyframes", []))
                + [boundary]
            },
        )
        return (positive, latent)


NODE_CLASS_MAPPINGS = {
    "H3RemakeConditioning": H3RemakeConditioning,
    "H3RemakeKeyframeUntil": H3RemakeKeyframeUntil,
    "H3RemakeNoise": H3RemakeNoise,
    "H3RemakePrefix": H3RemakePrefix,
    "H3RemakeHistory": H3RemakeHistory,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3RemakeConditioning": "Viggle Remake Conditioning",
    "H3RemakeKeyframeUntil": "Viggle Remake Keyframe Until",
    "H3RemakeNoise": "Viggle Remake Noise",
    "H3RemakePrefix": "Viggle Remake Prefix",
    "H3RemakeHistory": "Viggle Remake History",
}

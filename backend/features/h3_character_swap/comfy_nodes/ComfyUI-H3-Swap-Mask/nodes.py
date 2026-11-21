# SPDX-License-Identifier: Apache-2.0
"""Custom ComfyUI nodes for SAM 3.1 person mask selection, expansion, and H3 AV edit masking."""
from __future__ import annotations

FRAME_PER_TOKEN = (1, 4, 4, 4, 4)


def _normalize_mask_batch(masks):
    if masks.ndim == 2:
        return masks.unsqueeze(0)
    if masks.ndim > 3:
        return masks.reshape(-1, masks.shape[-2], masks.shape[-1])
    return masks


class H3SwapSelectMask:
    """Select one or top-N detected person masks by area or horizontal order."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "masks": ("MASK",),
                "selection": (
                    ["largest", "leftmost", "rightmost", "index", "top_n"],
                    {"default": "largest"},
                ),
                "index": ("INT", {"default": 0, "min": 0, "max": 64}),
                "max_subjects": ("INT", {"default": 1, "min": 1, "max": 9}),
            }
        }

    RETURN_TYPES = ("MASK",)
    RETURN_NAMES = ("selected_mask",)
    FUNCTION = "select"
    CATEGORY = "H3 Character Swap"

    def select(self, masks, selection="largest", index=0, max_subjects=1):
        import torch

        batch = _normalize_mask_batch(masks).float()
        if batch.shape[0] == 0:
            return (torch.ones((1, batch.shape[-2], batch.shape[-1]), device=batch.device, dtype=torch.float32),)

        h, w = int(batch.shape[-2]), int(batch.shape[-1])
        areas = batch.flatten(1).sum(dim=1)
        valid = [i for i in torch.where(areas > 4)[0].tolist()]
        if not valid:
            return (torch.ones((1, h, w), device=batch.device, dtype=torch.float32),)

        if selection == "top_n" or int(max_subjects) > 1:
            ordered = sorted(valid, key=lambda i: float(areas[i]), reverse=True)
            chosen = ordered[: max(1, int(max_subjects))]
            return (batch[chosen].contiguous(),)

        if selection == "largest":
            chosen_idx = max(valid, key=lambda i: float(areas[i]))
        elif selection in ("leftmost", "rightmost"):
            ordered = sorted(
                valid,
                key=lambda i: float(torch.where(batch[i] > 0.5)[1].float().mean())
                if (batch[i] > 0.5).any()
                else 0.0,
            )
            chosen_idx = ordered[0 if selection == "leftmost" else -1]
        else:
            pos = max(0, min(len(valid) - 1, int(index)))
            chosen_idx = valid[pos]

        return (batch[chosen_idx : chosen_idx + 1].contiguous(),)


class H3SwapExpandMask:
    """Align SAM track masks to clip frames and dilate foreground outward by Euclidean radius."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "masks": ("MASK",),
                "images": ("IMAGE",),
                "expansion_px": ("INT", {"default": 64, "min": 0, "max": 256}),
            }
        }

    RETURN_TYPES = ("MASK",)
    RETURN_NAMES = ("expanded_mask",)
    FUNCTION = "expand"
    CATEGORY = "H3 Character Swap"

    def expand(self, masks, images, expansion_px=64):
        import torch
        import torch.nn.functional as F

        target_t = int(images.shape[0])
        target_h = int(images.shape[1])
        target_w = int(images.shape[2])

        batch = _normalize_mask_batch(masks).float()
        if batch.shape[0] == 0:
            return (torch.ones((target_t, target_h, target_w), device=images.device, dtype=torch.float32),)

        if batch.shape[1] != target_h or batch.shape[2] != target_w:
            batch = F.interpolate(
                batch.unsqueeze(1),
                size=(target_h, target_w),
                mode="nearest",
            ).squeeze(1)

        if batch.shape[0] < target_t:
            pad_n = target_t - batch.shape[0]
            batch = torch.cat([batch, batch[-1:].repeat(pad_n, 1, 1)], dim=0)
        elif batch.shape[0] > target_t:
            batch = batch[:target_t]

        binary = batch > 0.5
        if not bool(binary.any()):
            return (torch.ones((target_t, target_h, target_w), device=images.device, dtype=torch.float32),)

        radius = int(expansion_px)
        if radius <= 0:
            return (binary.to(device=images.device, dtype=torch.float32),)

        try:
            import numpy as np
            from scipy.ndimage import distance_transform_edt

            bin_np = binary.detach().cpu().numpy()
            out_np = np.zeros_like(bin_np, dtype=np.float32)
            for idx in range(target_t):
                frame_mask = bin_np[idx]
                if frame_mask.any():
                    out_np[idx] = (distance_transform_edt(~frame_mask) <= radius).astype(np.float32)
            return (torch.from_numpy(out_np).to(device=images.device, dtype=torch.float32),)
        except ImportError:
            k = radius * 2 + 1
            dilated = F.max_pool2d(
                binary.float().unsqueeze(1),
                kernel_size=k,
                stride=1,
                padding=radius,
            ).squeeze(1)
            return ((dilated > 0.5).to(device=images.device, dtype=torch.float32),)


class H3SwapApplyEditMask:
    """Pool pixel-space person mask onto MiniMax-H3 AV latent grid with pristine background preservation."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "latent": ("LATENT",),
                "source_latent": ("LATENT",),
                "mask": ("MASK",),
            }
        }

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "apply"
    CATEGORY = "H3 Character Swap"

    def apply(self, latent, source_latent, mask):
        import torch
        import torch.nn.functional as F
        import comfy.nested_tensor

        samples = latent["samples"]
        if not samples.is_nested or len(samples.tensors) != 2:
            raise ValueError("H3SwapApplyEditMask expects a MiniMax-H3 nested video/audio latent")

        video, audio = samples.unbind()
        source = source_latent["samples"]
        if source.shape != video.shape:
            raise ValueError(
                f"Source VAE latent shape {tuple(source.shape)} does not match target video latent shape {tuple(video.shape)}"
            )

        mask_batch = _normalize_mask_batch(mask).float()
        t_pix = int(mask_batch.shape[0])
        t_lat, h_lat, w_lat = int(video.shape[2]), int(video.shape[3]), int(video.shape[4])

        chunks = []
        cursor = 0
        for k in range(t_lat):
            span = FRAME_PER_TOKEN[k % len(FRAME_PER_TOKEN)]
            if cursor < t_pix:
                end = min(t_pix, cursor + span)
                chunk = mask_batch[cursor:end]
            else:
                chunk = mask_batch[-1:]
            chunks.append(chunk.amax(dim=0, keepdim=True))
            cursor += span

        pooled_t = torch.cat(chunks, dim=0).unsqueeze(0)  # [1, T_lat, H, W]
        pooled_hw = F.adaptive_max_pool2d(pooled_t, (h_lat, w_lat))
        video_mask = (
            (pooled_hw > 0.5)
            .unsqueeze(1)
            .to(device=video.device, dtype=video.dtype)
            .expand_as(video)
            .contiguous()
        )
        audio_mask = torch.ones_like(audio)

        return (
            {
                **latent,
                "samples": comfy.nested_tensor.NestedTensor(
                    (source.to(device=video.device, dtype=video.dtype), audio)
                ),
                "noise_mask": comfy.nested_tensor.NestedTensor((video_mask, audio_mask)),
            },
        )


NODE_CLASS_MAPPINGS = {
    "H3SwapSelectMask": H3SwapSelectMask,
    "H3SwapExpandMask": H3SwapExpandMask,
    "H3SwapApplyEditMask": H3SwapApplyEditMask,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3SwapSelectMask": "H3 Swap Select Mask",
    "H3SwapExpandMask": "H3 Swap Expand Mask",
    "H3SwapApplyEditMask": "H3 Swap Apply Edit Mask",
}

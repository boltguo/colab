"""Unit tests for H3 Character Swap (Ref2VA + Turbo8 + V1.5 + SAM 3.1) nodes, schemas, graph builder, and bilingual notebook."""
import ast
import importlib.util
import json
from pathlib import Path
import unittest

from backend.features.h3_character_swap.runner import (
    AUDIO_VAE_FILENAME,
    CLIP_FILENAME,
    SAM_CHECKPOINT_FILENAME,
    SWAP_LORA_FILENAME,
    TURBO_LORA_FILENAME,
    UNET_FILENAME,
    VIDEO_VAE_FILENAME,
    build_character_swap_graph,
)
from backend.features.h3_character_swap.schemas import (
    DEFAULT_MASK_EXPANSION_PX,
    DEFAULT_SHIFT_AUDIO,
    DEFAULT_SHIFT_VIDEO,
    DEFAULT_SWAP_SCHEDULER,
    DEFAULT_SWAP_SIGMAS,
    DEFAULT_SWAP_STEPS,
    HISTORY_OVERLAP_FRAMES,
    CharacterSlot,
    H3CharacterSwapGenerateRequest,
    build_swap_prompt,
    compute_swap_dimensions,
    next_valid_frame_count,
    plan_swap_windows,
)

ROOT = Path(__file__).resolve().parents[1]
NODES_PATH = (
    ROOT
    / "backend"
    / "features"
    / "h3_character_swap"
    / "comfy_nodes"
    / "ComfyUI-H3-Swap-Mask"
    / "nodes.py"
)


class H3CharacterSwapUnitTests(unittest.TestCase):
    def test_bundled_mask_nodes_parse_and_export_mappings(self):
        source = NODES_PATH.read_text(encoding="utf-8")
        ast.parse(source)
        spec = importlib.util.spec_from_file_location("h3_swap_mask_nodes", NODES_PATH)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        self.assertEqual(
            set(mod.NODE_CLASS_MAPPINGS),
            {
                "H3SwapSelectMask",
                "H3SwapExpandMask",
                "H3SwapApplyEditMask",
            },
        )
        self.assertEqual(mod.FRAME_PER_TOKEN, (1, 4, 4, 4, 4))

    def test_canvas_geometry_and_window_planner(self):
        self.assertEqual(HISTORY_OVERLAP_FRAMES, 5)
        self.assertEqual(compute_swap_dimensions(1920, 1080, "480p", preserve_aspect=True), (864, 480))
        self.assertEqual(compute_swap_dimensions(1080, 1920, "480p", preserve_aspect=True), (480, 864))
        self.assertEqual(compute_swap_dimensions(1920, 1080, "480p", preserve_aspect=False), (832, 480))
        self.assertEqual(compute_swap_dimensions(1280, 720, "736p", preserve_aspect=False), (1280, 736))

        self.assertEqual(next_valid_frame_count(10), 22)
        self.assertEqual(next_valid_frame_count(120), 124)
        self.assertEqual(next_valid_frame_count(226), 226)
        self.assertEqual(next_valid_frame_count(345), 345)

        single = plan_swap_windows(120, max_window_frames=226, overlap_frames=5)
        self.assertEqual(
            single,
            [{"index": 0, "source_start": 0, "source_frames": 120, "history_frames": 0, "padded_frames": 124}],
        )

        chained = plan_swap_windows(240, max_window_frames=226, overlap_frames=5)
        self.assertEqual(len(chained), 2)
        self.assertEqual(chained[0]["source_frames"], 226)
        self.assertEqual(chained[0]["history_frames"], 0)
        self.assertEqual(chained[1]["source_start"], 226)
        self.assertEqual(chained[1]["source_frames"], 14)
        self.assertEqual(chained[1]["history_frames"], 5)
        self.assertEqual(chained[1]["padded_frames"], 22)

    def test_prompt_builder_single_multi_and_verbatim(self):
        default_single = build_swap_prompt(
            "single",
            [CharacterSlot(image="char1.png")],
            "",
            keep_audio=True,
        )
        self.assertIn("<Video 1>", default_single)
        self.assertIn("<Picture 1>", default_single)
        self.assertIn("<Audio 1>", default_single)
        self.assertIn("Replace the selected person in <Video 1>", default_single)

        single_detailed = build_swap_prompt(
            "single",
            [CharacterSlot(image="char1.png", name="Vega", target_description="dancer", appearance_description="white spacesuit")],
            "outdoor afternoon daylight",
            keep_audio=True,
        )
        self.assertIn("<Video 1>", single_detailed)
        self.assertIn("<Picture 1>", single_detailed)
        self.assertIn("<Audio 1>", single_detailed)
        self.assertIn("Vega, white spacesuit in <Picture 1>", single_detailed)
        self.assertIn("Replace dancer in <Video 1>", single_detailed)
        self.assertIn("outdoor afternoon daylight", single_detailed)

        multi_prompt = build_swap_prompt(
            "multi",
            [
                CharacterSlot(image="a.png", target_description="left dancer"),
                CharacterSlot(image="b.png", target_description="right singer"),
            ],
            "",
            keep_audio=False,
        )
        self.assertIn("<Picture 1>", multi_prompt)
        self.assertIn("<Picture 2>", multi_prompt)
        self.assertIn("left dancer", multi_prompt)
        self.assertIn("right singer", multi_prompt)
        self.assertNotIn("<Audio 1>", multi_prompt)

        verbatim = "Replace the dancer in <Video 1> with the knight from <Picture 1> in sunset light."
        self.assertEqual(
            build_swap_prompt("single", [CharacterSlot(image="a.png")], verbatim),
            verbatim,
        )

    def test_dynamic_comfy_graph_with_sam_mask_and_unmasked_variant(self):
        graph, labels, save_id = build_character_swap_graph(
            mode="multi",
            unet_name=UNET_FILENAME,
            staged_source="src.mp4",
            staged_refs=["ref1.png", "ref2.png"],
            prompt="test",
            padded_frames=124,
            width=832,
            height=480,
            seed=42,
            enable_edit_mask=True,
            keep_audio=True,
            staged_history="hist.mp4",
            history_frames=5,
            window_guides=[("guide.png", 5)],
        )
        self.assertEqual(save_id, "save")
        self.assertEqual(graph["model"]["class_type"], "UNETLoader")
        self.assertEqual(graph["model"]["inputs"]["unet_name"], UNET_FILENAME)
        self.assertEqual(graph["shift"]["class_type"], "MiniMaxH3SigmaShift")
        self.assertEqual(graph["shift"]["inputs"]["shift_video"], 12.0)
        self.assertEqual(graph["shift"]["inputs"]["shift_audio"], 3.0)
        self.assertEqual(graph["lora_turbo"]["class_type"], "LoraLoaderModelOnly")
        self.assertEqual(graph["lora_turbo"]["inputs"]["lora_name"], TURBO_LORA_FILENAME)
        self.assertEqual(graph["lora_swap"]["class_type"], "LoraLoaderModelOnly")
        self.assertEqual(graph["lora_swap"]["inputs"]["lora_name"], SWAP_LORA_FILENAME)
        self.assertEqual(graph["conditioning"]["class_type"], "MiniMaxH3ReferenceToVideo")
        self.assertEqual(graph["conditioning"]["inputs"]["ref_videos.ref_video_0"], ["frames", 0])
        self.assertEqual(graph["conditioning"]["inputs"]["ref_images.ref_image_0"], ["reference_1", 0])
        self.assertEqual(graph["conditioning"]["inputs"]["ref_images.ref_image_1"], ["reference_2", 0])
        self.assertEqual(graph["conditioning"]["inputs"]["audio_vae"], ["audio_vae", 0])
        self.assertEqual(graph["conditioning"]["inputs"]["ref_video_audios.ref_video_audio_0"], ["frames", 1])

        self.assertEqual(graph["sam"]["inputs"]["ckpt_name"], SAM_CHECKPOINT_FILENAME)
        self.assertEqual(graph["sam_detect"]["class_type"], "SAM3_Detect")
        self.assertEqual(graph["sam_select"]["class_type"], "H3SwapSelectMask")
        self.assertEqual(graph["sam_select"]["inputs"]["selection"], "top_n")
        self.assertEqual(graph["sam_select"]["inputs"]["max_subjects"], 2)
        self.assertEqual(graph["sam_track"]["class_type"], "SAM3_VideoTrack")
        self.assertEqual(graph["sam_mask"]["class_type"], "SAM3_TrackToMask")
        self.assertEqual(graph["sam_expand"]["class_type"], "H3SwapExpandMask")
        self.assertEqual(graph["sam_expand"]["inputs"]["expansion_px"], DEFAULT_MASK_EXPANSION_PX)
        self.assertEqual(graph["encode_source"]["class_type"], "VAEEncode")
        self.assertEqual(graph["edit_mask"]["class_type"], "H3SwapApplyEditMask")
        self.assertEqual(graph["sample"]["inputs"]["latent_image"], ["edit_mask", 0])

        self.assertEqual(graph["history"]["class_type"], "MiniMaxH3AddGuide")
        self.assertEqual(graph["history"]["inputs"]["latent"], ["edit_mask", 0])
        self.assertEqual(graph["history"]["inputs"]["frame_idx"], 0)
        self.assertEqual(graph["guide_apply_1"]["class_type"], "MiniMaxH3AddGuide")
        self.assertEqual(graph["guide_apply_1"]["inputs"]["frame_idx"], 5)
        self.assertEqual(graph["noise"]["class_type"], "RandomNoise")
        self.assertEqual(graph["guider"]["class_type"], "BasicGuider")
        self.assertEqual(graph["guider"]["inputs"]["model"], ["lora_swap", 0])
        self.assertEqual(graph["sampler"]["inputs"]["sampler_name"], "er_sde")
        self.assertEqual(graph["sigmas"]["class_type"], "BasicScheduler")
        self.assertEqual(graph["sigmas"]["inputs"]["scheduler"], DEFAULT_SWAP_SCHEDULER)
        self.assertEqual(graph["sigmas"]["inputs"]["steps"], DEFAULT_SWAP_STEPS)
        self.assertEqual(graph["sigmas"]["inputs"]["denoise"], 1.0)
        self.assertIn("sam_track", labels)
        self.assertIn("sample", labels)

        unmasked_graph, _, _ = build_character_swap_graph(
            unet_name=UNET_FILENAME,
            staged_source="src.mp4",
            staged_refs=["ref1.png"],
            prompt="test",
            padded_frames=124,
            width=832,
            height=480,
            seed=7,
            enable_edit_mask=False,
            keep_audio=False,
        )
        self.assertNotIn("sam", unmasked_graph)
        self.assertNotIn("edit_mask", unmasked_graph)
        self.assertEqual(unmasked_graph["sample"]["inputs"]["latent_image"], ["conditioning", 1])
        self.assertNotIn("audio_vae", unmasked_graph)
        self.assertNotIn("audio_vae", unmasked_graph["conditioning"]["inputs"])
        self.assertNotIn("ref_video_audios.ref_video_audio_0", unmasked_graph["conditioning"]["inputs"])

    def test_schema_validation_defaults_and_rejections(self):
        req = H3CharacterSwapGenerateRequest.model_validate(
            {"source_video": "v.mp4", "characters": [{"image": "c.png"}]}
        )
        self.assertEqual(req.sampler_name, "er_sde")
        self.assertEqual(req.steps, DEFAULT_SWAP_STEPS)
        self.assertEqual(req.scheduler, DEFAULT_SWAP_SCHEDULER)
        self.assertEqual(req.shift_video, DEFAULT_SHIFT_VIDEO)
        self.assertEqual(req.shift_audio, DEFAULT_SHIFT_AUDIO)
        self.assertEqual(req.turbo_lora_strength, 1.0)
        self.assertEqual(req.swap_lora_strength, 1.0)
        self.assertTrue(req.enable_edit_mask)
        self.assertEqual(req.mask_subject_prompt, "person")
        self.assertEqual(req.mask_selection, "largest")
        self.assertEqual(req.mask_expansion_px, DEFAULT_MASK_EXPANSION_PX)
        self.assertEqual(req.sigmas, DEFAULT_SWAP_SIGMAS)
        self.assertEqual(req.ref_image_size, "match")

        with self.assertRaises(ValueError):
            H3CharacterSwapGenerateRequest.model_validate({"source_video": "v.mp4", "characters": []})
        with self.assertRaises(ValueError):
            H3CharacterSwapGenerateRequest.model_validate(
                {"source_video": "v.mp4", "characters": [{"image": "c.png"}], "window_frames": 100}
            )
        with self.assertRaises(ValueError):
            H3CharacterSwapGenerateRequest.model_validate(
                {"source_video": "v.mp4", "characters": [{"image": "c.png"}], "sigmas": "1.0, 0.5"}
            )
        with self.assertRaises(ValueError):
            H3CharacterSwapGenerateRequest.model_validate(
                {
                    "source_video": "v.mp4",
                    "characters": [{"image": "c.png"}],
                    "guide_frames": [{"image": "g.png"}] * 5,
                }
            )

    def test_bilingual_notebook_is_valid_and_pinned(self):
        nb_path = ROOT / "notebooks" / "h3-character-swap" / "H3_Character_Swap.ipynb"
        self.assertTrue(nb_path.is_file(), f"Missing generated notebook {nb_path}")
        raw_nb = nb_path.read_text(encoding="utf-8")
        self.assertNotIn("ComfyUI-Viggle-Remake", raw_nb)
        self.assertNotIn("Viggle-Remake", raw_nb)

        nb = json.loads(raw_nb)
        self.assertEqual(len(nb["cells"]), 9)
        code_sources = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
        self.assertEqual(len(code_sources), 4)
        for idx, src in enumerate(code_sources, 1):
            ast.parse(src)
            if idx == 2:
                self.assertIn('BUNDLED_NODES_REL = "backend/features/h3_character_swap/comfy_nodes"', src)
                self.assertIn("sync_bundled_custom_nodes", src)
            if idx == 3:
                for weight in (
                    UNET_FILENAME,
                    TURBO_LORA_FILENAME,
                    SWAP_LORA_FILENAME,
                    SAM_CHECKPOINT_FILENAME,
                    CLIP_FILENAME,
                    VIDEO_VAE_FILENAME,
                    AUDIO_VAE_FILENAME,
                ):
                    self.assertIn(weight, src)
            if idx == 4:
                self.assertIn("MiniMaxH3ReferenceToVideo", src)
                self.assertIn("SAM3_VideoTrack", src)
                self.assertIn("H3SwapApplyEditMask", src)
                self.assertIn("--whitelist-custom-nodes", src)
                self.assertIn("ComfyUI-H3-Swap-Mask", src)
                self.assertIn("resolve_colab_proxy_url", src)
                self.assertIn("open_colab_proxy", src)
        self.assertNotIn("cloudflared", raw_nb)


if __name__ == "__main__":
    unittest.main()

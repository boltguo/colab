"""Unit tests for H3 Character Swap (Viggle Remake) nodes, schemas, graph builder, and bilingual notebook."""
import ast
import importlib.util
import json
from pathlib import Path
import unittest

from backend.features.h3_character_swap.runner import UNET_FILENAME, build_viggle_remake_graph
from backend.features.h3_character_swap.schemas import (
    CharacterSlot,
    H3CharacterSwapGenerateRequest,
    build_remake_prompt,
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
    / "ComfyUI-Viggle-Remake"
    / "nodes.py"
)


class H3CharacterSwapUnitTests(unittest.TestCase):
    def test_bundled_custom_nodes_parse_and_export_mappings(self):
        source = NODES_PATH.read_text(encoding="utf-8")
        ast.parse(source)
        spec = importlib.util.spec_from_file_location("viggle_remake_nodes", NODES_PATH)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        self.assertEqual(
            set(mod.NODE_CLASS_MAPPINGS),
            {
                "H3RemakeConditioning",
                "H3RemakeKeyframeUntil",
                "H3RemakeNoise",
                "H3RemakePrefix",
                "H3RemakeHistory",
            },
        )
        self.assertEqual(mod.stamps(226)[0], 0.25)
        self.assertEqual(len(mod.stamps(226)), 10)

    def test_canvas_geometry_and_window_planner(self):
        self.assertEqual(compute_swap_dimensions(1920, 1080, "480p", preserve_aspect=True), (864, 480))
        self.assertEqual(compute_swap_dimensions(1080, 1920, "480p", preserve_aspect=True), (480, 864))
        self.assertEqual(compute_swap_dimensions(1920, 1080, "480p", preserve_aspect=False), (832, 480))
        self.assertEqual(compute_swap_dimensions(1280, 720, "736p", preserve_aspect=False), (1280, 736))

        self.assertEqual(next_valid_frame_count(10), 22)
        self.assertEqual(next_valid_frame_count(120), 124)
        self.assertEqual(next_valid_frame_count(226), 226)
        self.assertEqual(next_valid_frame_count(345), 345)

        single = plan_swap_windows(120, max_window_frames=226, overlap_frames=18)
        self.assertEqual(
            single,
            [{"index": 0, "source_start": 0, "source_frames": 120, "history_frames": 0, "padded_frames": 124}],
        )

        chained = plan_swap_windows(240, max_window_frames=226, overlap_frames=18)
        self.assertEqual(len(chained), 2)
        self.assertEqual(chained[0]["source_frames"], 226)
        self.assertEqual(chained[0]["history_frames"], 0)
        self.assertEqual(chained[1]["source_start"], 226)
        self.assertEqual(chained[1]["source_frames"], 14)
        self.assertEqual(chained[1]["history_frames"], 18)
        self.assertEqual(chained[1]["padded_frames"], 39)

    def test_prompt_builder_single_multi_and_verbatim(self):
        single_prompt = build_remake_prompt(
            "single",
            [CharacterSlot(image="char1.png", name="Vega", target_description="dancer", appearance_description="white spacesuit")],
            "outdoor afternoon daylight",
            keep_audio=True,
        )
        self.assertIn("<Video 1>", single_prompt)
        self.assertIn("<Picture 1>", single_prompt)
        self.assertIn("<Subject 1>", single_prompt)
        self.assertIn("subject_definitions:", single_prompt)
        self.assertIn("non_diegetic_music:", single_prompt)

        multi_prompt = build_remake_prompt(
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
        self.assertIn("<Subject 1>", multi_prompt)
        self.assertIn("<Subject 2>", multi_prompt)
        self.assertIn("Silent output video", multi_prompt)

        verbatim = (
            "subject_definitions:\nx\nsummary:\nx\nretention_analysis:\nx\n"
            "detailed_description:\nx\noverall_soundscape:\nx\nnon_diegetic_music:\nN/A"
        )
        self.assertEqual(build_remake_prompt("single", [CharacterSlot(image="a.png")], verbatim), verbatim)

    def test_dynamic_comfy_graph_variants(self):
        graph, labels, save_id = build_viggle_remake_graph(
            unet_name=UNET_FILENAME,
            staged_source="src.mp4",
            staged_refs=["ref1.png", "ref2.png"],
            prompt="test",
            padded_frames=124,
            width=832,
            height=480,
            seed=42,
            staged_history="hist.mp4",
            history_frames=18,
            window_guides=[("guide.png", 18)],
        )
        self.assertEqual(save_id, "save")
        self.assertEqual(graph["conditioning"]["inputs"]["ref_1"], ["reference_1", 0])
        self.assertEqual(graph["conditioning"]["inputs"]["ref_2"], ["reference_2", 0])
        self.assertEqual(graph["history"]["class_type"], "H3RemakeHistory")
        self.assertEqual(graph["guide_apply_1"]["class_type"], "MiniMaxH3AddGuide")
        self.assertEqual(graph["guide_apply_1"]["inputs"]["frame_idx"], 18)
        self.assertIn("sample", labels)

    def test_schema_validation_rejects_invalid_inputs(self):
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
        nb = json.loads(nb_path.read_text(encoding="utf-8"))
        self.assertEqual(len(nb["cells"]), 9)
        code_sources = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
        self.assertEqual(len(code_sources), 4)
        for idx, src in enumerate(code_sources, 1):
            ast.parse(src)
            if idx == 2:
                self.assertIn("sync_bundled_custom_nodes", src)
                self.assertIn("backend/features/h3_character_swap/comfy_nodes", src)
            if idx == 3:
                self.assertIn("viggle_remake_swap_pruned_int8_convrot.safetensors", src)
                self.assertIn("qwen3vl_32b_minimax_h3_int8_convrot.safetensors", src)
            if idx == 4:
                self.assertIn("--whitelist-custom-nodes", src)
                self.assertIn("ComfyUI-Viggle-Remake", src)
                self.assertIn("Quick Tunnel (ephemeral)", src)


if __name__ == "__main__":
    unittest.main()

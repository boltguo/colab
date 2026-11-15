"""Regression checks for reference ordering and resolution intent, without model weights."""
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from pydantic import ValidationError
from PIL import Image

from backend.core.storage import MediaStorage
from backend.features.qwen_image_2_1.runner import QwenImageRunner
from backend.features.qwen_image_2_1.schemas import QwenImageGenerateRequest


class QwenImageRequestTests(unittest.TestCase):
    def test_official_ten_reference_limit_reaches_engine_input_ten(self):
        names = [f"reference-{i}.png" for i in range(10)]
        req = QwenImageGenerateRequest(mode="img2img", prompt="组合全部参考图", reference_images=names)
        with self.assertRaises(ValidationError):
            QwenImageGenerateRequest(mode="img2img", prompt="组合", reference_images=names + ["eleventh.png"])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runner = QwenImageRunner(MediaStorage(root), root, mock_mode=True)
            graph, _, _ = runner._build_comfy_graph(
                req, actual_seed=42, staged_ref_names=names, resolved_loras=[],
                canvas_w=2048, canvas_h=2048, ref_res=2048, kv_device="auto",
            )
            self.assertEqual(graph["6"]["inputs"]["images.image_10"], ["ref_alpha_10", 0])
            self.assertEqual(graph["load_ref_10"]["inputs"]["image"], names[9])
            self.assertEqual(graph["ref_alpha_10"]["class_type"], "JoinImageWithAlpha")
            self.assertEqual(graph["ref_alpha_10"]["inputs"], {"image": ["load_ref_10", 0], "alpha": ["load_ref_10", 1]})

    def test_reference_geometry_matches_exif_orientation_and_invalid_files_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "portrait.jpg"
            image = Image.new("RGB", (96, 64))
            exif = image.getexif()
            exif[274] = 6
            image.save(source, exif=exif)
            self.assertEqual(QwenImageRunner._probe_image_dims(source), (64, 96))
            source.write_bytes(b"invalid image")
            with self.assertRaisesRegex(ValueError, "有效"):
                QwenImageRunner._probe_image_dims(source)

    def test_original_geometry_is_not_silently_clamped_away_from_reference_latent(self):
        req = QwenImageGenerateRequest(
            mode="img2img", prompt="保持尺寸", reference_images=["wide.png"],
            resolution_tier="original", aspect_ratio="match_input",
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runner = QwenImageRunner(MediaStorage(root), root, mock_mode=True)
            with patch.object(runner, "_probe_image_dims", return_value=(6000, 4000)):
                with self.assertRaisesRegex(ValueError, "4096"):
                    runner._resolve_target_dimensions(req, [root / "wide.png"])

    def test_blank_prompt_is_rejected_before_queueing(self):
        with self.assertRaisesRegex(ValidationError, "请输入"):
            QwenImageGenerateRequest(prompt=" \n\t ")

    def test_sparse_references_cannot_silently_renumber_prompt_tags(self):
        for refs in (["", "second.png"], ["first.png", " ", "third.png"]):
            with self.subTest(refs=refs), self.assertRaisesRegex(ValidationError, "不能留空"):
                QwenImageGenerateRequest(mode="img2img", prompt="编辑 <image2>", reference_images=refs)

    def test_legacy_reference_fields_follow_the_same_ordering_rule(self):
        with self.assertRaisesRegex(ValidationError, "不能留空"):
            QwenImageGenerateRequest(mode="img2img", prompt="编辑 <image2>", image_2="second.png")

    def test_trailing_empty_reference_does_not_shift_existing_tags(self):
        request = QwenImageGenerateRequest(
            mode="img2img", prompt=" 编辑 <image1> ", reference_images=["first.png", ""],
        )
        self.assertEqual(request.effective_references(), ["first.png"])
        self.assertEqual(request.prompt, "编辑 <image1>")

    def test_original_resolution_requires_reference_geometry(self):
        with self.assertRaisesRegex(ValidationError, "原图分辨率"):
            QwenImageGenerateRequest(prompt="生成", resolution_tier="original")
        request = QwenImageGenerateRequest(
            mode="img2img", prompt="编辑", reference_images=["first.png"],
            resolution_tier="original", aspect_ratio="match_input",
        )
        self.assertEqual(request.resolution_tier, "original")


if __name__ == "__main__":
    unittest.main()

"""Regression checks for reference ordering and resolution intent, without model weights."""
import unittest

from pydantic import ValidationError

from backend.features.qwen_image_2_1.schemas import QwenImageGenerateRequest


class QwenImageRequestTests(unittest.TestCase):
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

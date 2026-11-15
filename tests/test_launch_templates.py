"""Exercise notebook restart decisions and release guards without starting services or publishing."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import textwrap
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ("step4_app", "step4_comfy_app", "step4_vllm")


def template_ast(name):
    source = (ROOT / "tools/templates" / f"{name}.py").read_text()
    values = {"REQUIRED_NODES": "set()", "SAMPLE_REQUEST_JSON": "{}"}
    source = re.sub(r"\{\{([A-Z_]+)\}\}", lambda match: values.get(match[1], ""), source)
    return ast.parse(source)


def fingerprint(name, *, release="v0.1.1:abc", key="key-one", environment=None):
    namespace = {
        "json": json, "hashlib": hashlib, "APP_DIR": Path("/content/app"),
        "cmd": ["python", "backend/run_server.py"],
        "app_cmd": ["python", "backend/run_server.py"],
        "app_api_key": key,
        "env_overrides": {"COLAB_API_KEY": key, "COLAB_FEATURE": "feature", **(environment or {})},
        "read_text": lambda _: release,
    }
    assignment = next(
        node for node in template_ast(name).body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id in ("app_fingerprint", "launch_fingerprint") for target in node.targets)
    )
    exec(compile(ast.Module(body=[assignment], type_ignores=[]), name, "exec"), namespace)
    return namespace[assignment.targets[0].id]


class NotebookRestartTests(unittest.TestCase):
    def test_updated_bundle_changes_the_restart_fingerprint(self):
        for template in TEMPLATES:
            with self.subTest(template=template):
                self.assertNotEqual(fingerprint(template), fingerprint(template, release="v0.1.2:def"))

    def test_rotating_enabled_api_key_restarts_without_storing_the_key(self):
        for template in TEMPLATES:
            with self.subTest(template=template):
                first = fingerprint(template, key="private-key-one")
                second = fingerprint(template, key="private-key-two")
                self.assertNotEqual(first, second)
                self.assertNotIn("private-key", first)
                self.assertNotIn("private-key", second)
                self.assertNotIn("COLAB_API_KEY", first)

    def test_engine_environment_changes_restart_the_gateway(self):
        for template in TEMPLATES:
            with self.subTest(template=template):
                self.assertNotEqual(
                    fingerprint(template, environment={"ENGINE_BASE": "http://127.0.0.1:8189"}),
                    fingerprint(template, environment={"ENGINE_BASE": "http://127.0.0.1:8190"}),
                )

    def test_unchanged_configuration_has_a_stable_fingerprint(self):
        for template in TEMPLATES:
            with self.subTest(template=template):
                self.assertEqual(fingerprint(template), fingerprint(template))


class MediaPrerequisiteTests(unittest.TestCase):
    def run_guard(self, template, feature, missing):
        guard = next(
            node for node in template_ast(template).body
            if isinstance(node, ast.If)
            and any(isinstance(child, ast.Name) and child.id == "missing_media_tools" for child in ast.walk(node))
        )
        namespace = {
            "FEATURE_NAME": feature,
            "shutil": SimpleNamespace(which=lambda name: None if name in missing else f"/usr/bin/{name}"),
        }
        exec(compile(ast.Module(body=[guard], type_ignores=[]), template, "exec"), namespace)

    def test_required_media_tools_fail_before_model_loading_with_recovery_hint(self):
        for template, feature in (("step4_app", "indextts-2.5"), ("step4_comfy_app", "seedvr2"), ("step4_comfy_app", "minimax-h3")):
            with self.subTest(feature=feature), self.assertRaisesRegex(RuntimeError, "ffprobe.*apt-get"):
                self.run_guard(template, feature, {"ffprobe"})

    def test_installed_tools_allow_launch(self):
        self.run_guard("step4_app", "indextts-2.5", set())
        self.run_guard("step4_comfy_app", "minimax-h3", set())

    def test_image_studio_does_not_require_video_tools(self):
        self.run_guard("step4_comfy_app", "qwen-image-2.1", {"ffmpeg", "ffprobe"})


class ReleaseGuardTests(unittest.TestCase):
    def run_guard(self, *, tag="v0.1.1", existing_tag="", existing_release="", api_fail="0"):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        step = workflow.split("- name: Validate new release tag", 1)[1].split("\n      - name:", 1)[0]
        script = textwrap.dedent(step.split("run: |\n", 1)[1])
        stubs = '''
git() {
  if [[ "$1" == "ls-remote" ]]; then printf '%s' "$EXISTING_GIT_TAG"; fi
}
gh() {
  if [[ "$API_FAIL" == "1" ]]; then return 1; fi
  printf '%s\\n' "$EXISTING_RELEASE_TAG"
}
'''
        return subprocess.run(
            ["bash", "-euo", "pipefail", "-c", stubs + script],
            env={**os.environ, "TAG_NAME": tag, "GITHUB_REPOSITORY": "example/project",
                 "EXISTING_GIT_TAG": existing_tag, "EXISTING_RELEASE_TAG": existing_release, "API_FAIL": api_fail},
            capture_output=True, text=True, timeout=10,
        )

    def test_new_version_is_allowed(self):
        for tag in ("v0.1.1", "v0.1.1-rc.1"):
            with self.subTest(tag=tag):
                self.assertEqual(self.run_guard(tag=tag).returncode, 0)

    def test_existing_tag_or_release_cannot_be_overwritten(self):
        self.assertNotEqual(self.run_guard(existing_tag="abc refs/tags/v0.1.1").returncode, 0)
        self.assertNotEqual(self.run_guard(existing_release="v0.1.1").returncode, 0)

    def test_tag_input_is_not_executed_as_shell_code(self):
        result = self.run_guard(tag="v0.1.1$(printf injected)")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("injected", result.stdout)

    def test_metadata_failure_stops_the_release(self):
        self.assertNotEqual(self.run_guard(api_fail="1").returncode, 0)


if __name__ == "__main__":
    unittest.main()

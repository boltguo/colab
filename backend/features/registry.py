"""Feature plugin registry mapping `--feature <name>` to its isolated plugin module.

Uses lazy `importlib.import_module` so per-feature release tarballs (`app-<feature>.tar.gz`)
only need their own `backend/features/<module>` directory without cross-feature imports.
"""
import importlib
from pathlib import Path
from typing import Dict, Optional, Tuple

from ..core.app_factory import FeaturePlugin
from ..core.storage import MediaStorage

FEATURE_MODULES: Dict[str, Tuple[str, str]] = {
    "indextts-2.5": ("backend.features.indextts_2_5.plugin", "INDEXTTS_2_5_PLUGIN"),
    "minimax-h3": ("backend.features.minimax_h3.plugin", "MINIMAX_H3_PLUGIN"),
    "qwen-image-2.1": ("backend.features.qwen_image_2_1.plugin", "QWEN_IMAGE_2_1_PLUGIN"),
    "qwen3.8-27b": ("backend.features.qwen3_8_27b.plugin", "QWEN_3_8_27B_PLUGIN"),
    "seedvr2": ("backend.features.seedvr2.plugin", "SEEDVR2_PLUGIN"),
}


def get_feature_plugin(feature_name: str) -> FeaturePlugin:
    entry = FEATURE_MODULES.get(feature_name)
    if not entry:
        supported = ", ".join(sorted(FEATURE_MODULES))
        raise ValueError(f"未知功能模块 '{feature_name}'，当前已支持：{supported}")
    mod_path, attr_name = entry
    module = importlib.import_module(mod_path)
    return getattr(module, attr_name)


def load_feature_plugin(
    feature_name: str,
    data_dir: Optional[Path] = None,
    storage: Optional[MediaStorage] = None,
    mock_mode: bool = False,
) -> FeaturePlugin:
    _ = (data_dir, storage, mock_mode)
    return get_feature_plugin(feature_name)

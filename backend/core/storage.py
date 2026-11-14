"""Media upload, preset registration, and generated output storage."""
from datetime import datetime, timezone
import mimetypes
from pathlib import Path
import re
import shutil
from typing import Dict, List, Optional, Tuple
import uuid

from fastapi import HTTPException, UploadFile

from .models import PresetItem, UploadedFileResponse
from .security import ensure_safe_dir, ensure_safe_path

ALLOWED_EXTENSIONS = {
    ".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".webm",
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".mp4", ".mov", ".mkv",
}
MAX_UPLOAD_BYTES = 512 * 1024 * 1024  # 512 MiB
SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


class MediaStorage:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = ensure_safe_dir(base_dir)
        self.uploads_dir = ensure_safe_dir(self.base_dir / "uploads", stop_at=self.base_dir)
        self.outputs_dir = ensure_safe_dir(self.base_dir / "outputs", stop_at=self.base_dir)
        self._presets: Dict[str, Tuple[PresetItem, Path]] = {}

    def register_preset(
        self,
        preset_id: str,
        file_path: Path,
        label: str,
        description: str = "",
        kind: str = "audio",
    ) -> None:
        ensure_safe_path(file_path)
        if not file_path.is_file():
            return
        full_id = f"preset:{preset_id}"
        item = PresetItem(
            id=full_id,
            label=label,
            description=description,
            kind=kind,  # type: ignore[arg-type]
            url=f"/api/v1/presets/{preset_id}",
            filename=file_path.name,
        )
        self._presets[preset_id] = (item, file_path)

    def list_presets(self) -> List[PresetItem]:
        return [pair[0] for pair in self._presets.values()]

    def get_preset_path(self, preset_id: str) -> Path:
        entry = self._presets.get(preset_id)
        if not entry:
            raise HTTPException(status_code=404, detail=f"未找到预置素材：{preset_id}")
        path = ensure_safe_path(entry[1])
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"预置素材文件缺失：{preset_id}")
        return path

    async def save_upload(self, upload: UploadFile) -> UploadedFileResponse:
        orig_name = Path(upload.filename or "upload.bin").name
        ext = Path(orig_name).suffix.lower()
        if not ext and upload.content_type:
            guessed = mimetypes.guess_extension(upload.content_type.split(";")[0].strip())
            ext = (guessed or "").lower()
        if ext == ".oga":
            ext = ".ogg"
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件格式 '{ext or 'unknown'}'，支持：{', '.join(sorted(ALLOWED_EXTENSIONS))}",
            )

        file_id = f"{uuid.uuid4().hex[:16]}{ext}"
        dest = ensure_safe_path(self.uploads_dir / file_id, stop_at=self.base_dir)

        total = 0
        try:
            with dest.open("wb") as out:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail="上传文件超过 512MB 限制。")
                    out.write(chunk)
        except Exception:
            if dest.exists():
                dest.unlink()
            raise

        if total == 0:
            if dest.exists():
                dest.unlink()
            raise HTTPException(status_code=400, detail="上传文件为空。")

        ctype = upload.content_type or mimetypes.guess_type(orig_name)[0] or "application/octet-stream"
        now = datetime.now(timezone.utc).isoformat()
        return UploadedFileResponse(
            file_id=file_id,
            filename=orig_name,
            content_type=ctype,
            size_bytes=total,
            url=f"/api/v1/files/{file_id}",
            created_at=now,
        )

    def get_upload_path(self, file_id: str) -> Path:
        if not SAFE_ID_RE.match(file_id) or Path(file_id).name != file_id:
            raise HTTPException(status_code=400, detail="非法的文件 ID。")
        target = ensure_safe_path(self.uploads_dir / file_id, stop_at=self.base_dir)
        if not target.is_file():
            raise HTTPException(status_code=404, detail=f"找不到已上传文件：{file_id}")
        return target

    def resolve_input_ref(self, ref: str) -> Path:
        ref = (ref or "").strip()
        if not ref:
            raise ValueError("未提供输入文件引用。")
        if ref.startswith("preset:"):
            preset_key = ref.split(":", 1)[1]
            entry = self._presets.get(preset_key)
            if not entry or not entry[1].is_file():
                raise ValueError(f"预置素材 '{ref}' 不存在。")
            return ensure_safe_path(entry[1])
        if ref.startswith("output:"):
            out_name = ref.split(":", 1)[1].strip()
            if not SAFE_ID_RE.match(out_name) or Path(out_name).name != out_name:
                raise ValueError(f"非法的历史输出引用 '{ref}'。")
            out_target = ensure_safe_path(self.outputs_dir / out_name, stop_at=self.base_dir)
            if not out_target.is_file():
                raise ValueError(f"找不到历史生成文件 '{out_name}'。")
            return out_target
        if not SAFE_ID_RE.match(ref) or Path(ref).name != ref:
            raise ValueError(f"非法的文件引用 '{ref}'，请先调用 POST /api/v1/files 上传获取 file_id。")
        target = ensure_safe_path(self.uploads_dir / ref, stop_at=self.base_dir)
        if not target.is_file():
            raise ValueError(f"找不到上传文件 '{ref}'，请重新上传。")
        return target

    def allocate_output_path(self, prefix: str, ext: str) -> Tuple[str, Path]:
        clean_prefix = re.sub(r"[^a-zA-Z0-9_-]", "_", prefix).strip("_") or "out"
        clean_ext = ext if ext.startswith(".") else f".{ext}"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{clean_prefix}_{stamp}_{uuid.uuid4().hex[:8]}{clean_ext}"
        dest = ensure_safe_path(self.outputs_dir / filename, stop_at=self.base_dir)
        return filename, dest

    def get_output_path(self, filename: str) -> Path:
        if not SAFE_ID_RE.match(filename) or Path(filename).name != filename:
            raise HTTPException(status_code=400, detail="非法的输出文件名。")
        target = ensure_safe_path(self.outputs_dir / filename, stop_at=self.base_dir)
        if not target.is_file():
            raise HTTPException(status_code=404, detail=f"输出文件不存在：{filename}")
        return target

    def copy_to_output(self, src: Path, prefix: str, ext: str) -> Tuple[str, Path]:
        filename, dest = self.allocate_output_path(prefix, ext)
        shutil.copy2(src, dest)
        return filename, dest

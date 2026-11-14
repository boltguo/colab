"""On-demand Dynamic LoRA Catalog, Downloader, Uploader, and Validator.

Supports:
1. Built-in curated LoRAs per feature (pinned Hugging Face repo + revision + expected size).
2. Arbitrary Hugging Face repo IDs (`owner/repo`, `owner/repo::file.safetensors`, or HF resolve/blob URLs).
3. Civitai / direct HTTPS `.safetensors` download URLs (with optional Bearer token).
4. Local `.safetensors` file uploads via multipart form.
5. SafeTensors binary magic-header verification (strictly rejecting `.ckpt`/`.pt` pickle files),
   symlink rejection, disk-space precheck, and one-click cache deletion.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request

from fastapi import HTTPException, UploadFile
from pydantic import BaseModel, Field

from .security import ensure_safe_dir, ensure_safe_path

ProgressFn = Callable[[float, str], None]

SAFE_LORA_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]+$")
MAX_LORA_UPLOAD_BYTES = 4 * 1024 * 1024 * 1024  # 4 GiB
MIN_FREE_HEADROOM_BYTES = 1536 * 1024 * 1024  # Keep >= 1.5 GiB free on /content
HF_URL_RE = re.compile(
    r"^https?://huggingface\.co/([^/]+/[^/]+)/(?:resolve|blob)/([^/]+)/(.+)$"
)


@dataclass(frozen=True)
class CuratedLoraSpec:
    id: str
    filename: str
    label: str
    description: str
    repo_id: str
    revision: str
    repo_filename: str
    expected_size: Optional[int] = None
    recommended_strength: float = 0.85
    trigger_words: Tuple[str, ...] = ()
    tags: Tuple[str, ...] = ()


class LoraCatalogEntry(BaseModel):
    id: str
    filename: str
    label: str
    description: str = ""
    installed: bool
    curated: bool = False
    size_bytes: Optional[int] = None
    recommended_strength: float = 1.0
    trigger_words: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    source_hint: str = ""


class LoraListResponse(BaseModel):
    loras_dir: str
    free_disk_gb: float
    total_disk_gb: float
    items: List[LoraCatalogEntry]


class LoraDownloadRequest(BaseModel):
    source: str = Field(
        ...,
        min_length=2,
        max_length=1024,
        description=(
            "支持：① 内置目录 ID 或文件名；② Hugging Face 仓库（如 owner/repo 或 owner/repo::xxx.safetensors）；"
            "③ Hugging Face 文件链接（resolve/blob URL）；④ Civitai 或任意直链 HTTPS .safetensors 地址。"
        ),
    )
    filename: Optional[str] = Field(
        default=None,
        max_length=180,
        description="可选：保存到 loras 目录的目标文件名（必须以 .safetensors 结尾）。",
    )
    revision: Optional[str] = Field(
        default=None,
        max_length=128,
        description="可选：Hugging Face 分支或 40 位 Commit SHA（默认 main）。",
    )
    token: Optional[str] = Field(
        default=None,
        max_length=512,
        description="可选：访问受限 Hugging Face 仓库或 Civitai 下载所需的 API Token（仅本次下载使用，不落盘）。",
    )


def sanitize_lora_filename(raw_name: str) -> str:
    base = Path(raw_name.strip()).name
    if not base:
        raise ValueError("LoRA 文件名不能为空。")
    lower = base.lower()
    for bad_ext in (".ckpt", ".pt", ".pth", ".bin", ".pkl", ".pickle"):
        if lower.endswith(bad_ext):
            raise ValueError(
                f"出于安全策略拒绝加载 '{base}'：仅允许安全张量格式 .safetensors，禁止包含可执行代码的 Pickle 权重。"
            )
    if not lower.endswith(".safetensors"):
        base = f"{base}.safetensors"
    stem = base[: -len(".safetensors")]
    clean_stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", stem).strip("._-") or "custom_lora"
    clean_name = f"{clean_stem[:120]}.safetensors"
    if not SAFE_LORA_NAME_RE.match(clean_name):
        raise ValueError(f"非法的 LoRA 文件名：{raw_name}")
    return clean_name


def verify_safetensors_file(path: Path, expected_size: Optional[int] = None) -> int:
    """Validate that `path` is a genuine SafeTensors file (not HTML error page or Pickle)."""
    ensure_safe_path(path)
    if not path.is_file():
        raise ValueError(f"未找到权重文件：{path.name}")
    actual_size = path.stat().st_size
    if actual_size < 16:
        raise ValueError(f"文件过小（{actual_size} B），不是有效的 .safetensors 权重。")
    if expected_size is not None and actual_size != expected_size:
        raise ValueError(
            f"权重文件大小校验不通过：预期 {expected_size} 字节，实际 {actual_size} 字节。"
        )

    with path.open("rb") as f:
        head = f.read(16)
        # Reject ZIP/PyTorch pickle (`PK\x03\x04`), pickle protocol (`\x80`), or HTML (`<!DO`, `<htm`)
        if head.startswith((b"PK\x03\x04", b"\x80\x02", b"\x80\x03", b"\x80\x04", b"\x80\x05")):
            raise ValueError("检测到 Pickle/ZIP 序列化头，拒绝加载非 SafeTensors 权重文件。")
        if head.lstrip().lower().startswith((b"<!doctype", b"<html", b"{\"error\"")):
            raise ValueError("下载内容为网页或错误响应（可能需要填写 Hugging Face / Civitai Token），请检查链接。")

        header_len = struct.unpack("<Q", head[:8])[0]
        if header_len == 0 or header_len > 100 * 1024 * 1024 or 8 + header_len > actual_size:
            raise ValueError("SafeTensors 元数据头长度非法，文件可能已损坏或并非 .safetensors 格式。")

        f.seek(8)
        json_preview = f.read(min(header_len, 2048)).lstrip()
        if not json_preview.startswith(b"{"):
            raise ValueError("SafeTensors JSON 头部校验失败。")
    return actual_size


def write_mock_safetensors(dest: Path, metadata: Optional[Dict[str, str]] = None) -> int:
    """Create a tiny valid SafeTensors file for local --mock mode testing without downloading hundreds of MB."""
    meta = {"__metadata__": metadata or {"mock": "true", "format": "pt"}}
    # Include one dummy 4-byte float32 tensor so any SafeTensors parser accepts it cleanly
    meta["mock_weight"] = {
        "dtype": "F32",
        "shape": [1],
        "data_offsets": [0, 4],
    }
    header_bytes = json.dumps(meta, separators=(",", ":")).encode("utf-8")
    # Pad header to 8-byte alignment per SafeTensors spec
    pad = (8 - (len(header_bytes) % 8)) % 8
    header_bytes += b" " * pad
    payload = struct.pack("<Q", len(header_bytes)) + header_bytes + struct.pack("<f", 1.0)
    dest.write_bytes(payload)
    return len(payload)


class LoraManager:
    """Manages curated & user-supplied `.safetensors` LoRA files on disk."""

    def __init__(
        self,
        loras_dir: Path,
        curated: Optional[List[CuratedLoraSpec]] = None,
        mock_mode: bool = False,
    ) -> None:
        self.loras_dir = ensure_safe_dir(loras_dir)
        self.curated: Dict[str, CuratedLoraSpec] = {}
        self.curated_by_filename: Dict[str, CuratedLoraSpec] = {}
        for spec in curated or []:
            self.curated[spec.id] = spec
            self.curated_by_filename[spec.filename] = spec
        self.mock_mode = mock_mode

    def list_all(self) -> LoraListResponse:
        ensure_safe_dir(self.loras_dir)
        usage = shutil.disk_usage(self.loras_dir)
        free_gb = round(usage.free / (1024**3), 2)
        total_gb = round(usage.total / (1024**3), 2)

        disk_files: Dict[str, Path] = {}
        for entry in sorted(self.loras_dir.iterdir(), key=lambda p: p.name.lower()):
            if entry.is_symlink() or not entry.is_file():
                continue
            if entry.name.lower().endswith(".safetensors") and not entry.name.startswith("."):
                disk_files[entry.name] = entry

        items: List[LoraCatalogEntry] = []
        seen_filenames = set()

        # 1. Curated entries first
        for spec in self.curated.values():
            seen_filenames.add(spec.filename)
            on_disk = disk_files.get(spec.filename)
            installed = on_disk is not None
            size_bytes = on_disk.stat().st_size if on_disk else spec.expected_size
            items.append(
                LoraCatalogEntry(
                    id=spec.id,
                    filename=spec.filename,
                    label=spec.label,
                    description=spec.description,
                    installed=installed,
                    curated=True,
                    size_bytes=size_bytes,
                    recommended_strength=spec.recommended_strength,
                    trigger_words=list(spec.trigger_words),
                    tags=list(spec.tags),
                    source_hint=f"{spec.repo_id}@{spec.revision[:10]}",
                )
            )

        # 2. Custom downloaded / uploaded LoRAs on disk
        for fname, fpath in disk_files.items():
            if fname in seen_filenames:
                continue
            stem = fname[: -len(".safetensors")]
            items.append(
                LoraCatalogEntry(
                    id=f"local:{fname}",
                    filename=fname,
                    label=stem,
                    description="本地上传或外部在线拉取的自定义 LoRA 权重",
                    installed=True,
                    curated=False,
                    size_bytes=fpath.stat().st_size,
                    recommended_strength=0.85,
                    trigger_words=[],
                    tags=["自定义"],
                    source_hint="本地已缓存",
                )
            )

        return LoraListResponse(
            loras_dir=str(self.loras_dir),
            free_disk_gb=free_gb,
            total_disk_gb=total_gb,
            items=items,
        )

    def is_installed(self, filename: str) -> bool:
        clean = sanitize_lora_filename(filename)
        target = ensure_safe_path(self.loras_dir / clean, stop_at=self.loras_dir)
        return target.is_file()

    async def save_upload(self, upload: UploadFile) -> LoraCatalogEntry:
        orig_name = Path(upload.filename or "").name
        try:
            clean_name = sanitize_lora_filename(orig_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        usage = shutil.disk_usage(self.loras_dir)
        if usage.free < MIN_FREE_HEADROOM_BYTES:
            raise HTTPException(
                status_code=507,
                detail=f"实例磁盘剩余空间不足（仅剩 {usage.free / 1024**3:.2f} GB），请先清理不用的 LoRA。",
            )

        tmp_path = ensure_safe_path(
            self.loras_dir / f".upload_{ clean_name }_{ int(time.time() * 1000) }.part",
            stop_at=self.loras_dir,
        )
        dest_path = ensure_safe_path(self.loras_dir / clean_name, stop_at=self.loras_dir)

        total = 0
        try:
            with tmp_path.open("wb") as out:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_LORA_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail="单个 LoRA 文件超过 4GB 上限。")
                    out.write(chunk)
            verify_safetensors_file(tmp_path)
            tmp_path.replace(dest_path)
        except HTTPException:
            if tmp_path.exists():
                tmp_path.unlink()
            raise
        except Exception as exc:
            if tmp_path.exists():
                tmp_path.unlink()
            raise HTTPException(status_code=400, detail=f"LoRA 校验失败：{exc}") from exc

        return self._entry_for_file(dest_path)

    def delete_lora(self, filename: str) -> Dict[str, Any]:
        try:
            clean_name = sanitize_lora_filename(filename)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        target = ensure_safe_path(self.loras_dir / clean_name, stop_at=self.loras_dir)
        if not target.is_file():
            raise HTTPException(status_code=404, detail=f"未找到已缓存的 LoRA：{clean_name}")
        freed = target.stat().st_size
        target.unlink()
        return {"deleted": clean_name, "freed_bytes": freed}

    def ensure_available(
        self,
        source_or_name: str,
        *,
        filename: Optional[str] = None,
        revision: Optional[str] = None,
        token: Optional[str] = None,
        on_progress: Optional[ProgressFn] = None,
        progress_range: Tuple[float, float] = (0.04, 0.96),
    ) -> LoraCatalogEntry:
        """Resolve or download a LoRA by curated ID, installed filename, HF repo, or direct URL."""
        raw = source_or_name.strip()
        if not raw:
            raise ValueError("LoRA 来源不能为空。")

        # Case 1: Matches a curated ID or curated filename
        curated_spec = self.curated.get(raw) or self.curated_by_filename.get(raw)
        if curated_spec is not None:
            dest = ensure_safe_path(self.loras_dir / curated_spec.filename, stop_at=self.loras_dir)
            if dest.is_file():
                if not self.mock_mode and curated_spec.expected_size:
                    if dest.stat().st_size == curated_spec.expected_size:
                        return self._entry_for_file(dest)
                else:
                    return self._entry_for_file(dest)
            return self._download_curated(curated_spec, token=token, on_progress=on_progress, progress_range=progress_range)

        # Case 2: Already installed local filename
        if "://" not in raw and "/" not in raw and "::" not in raw:
            clean = sanitize_lora_filename(raw)
            dest = ensure_safe_path(self.loras_dir / clean, stop_at=self.loras_dir)
            if dest.is_file():
                return self._entry_for_file(dest)
            raise ValueError(
                f"本地尚未安装 LoRA '{clean}'。请提供 Hugging Face 仓库（如 owner/repo）、直链 URL，或先上传该 .safetensors 文件。"
            )

        # Case 3: Hugging Face blob/resolve URL -> convert to direct resolve URL
        hf_match = HF_URL_RE.match(raw)
        if hf_match:
            repo_id, url_rev, repo_file_raw = hf_match.group(1), hf_match.group(2), hf_match.group(3)
            repo_file = urllib.parse.unquote(repo_file_raw.split("?", 1)[0])
            target_name = sanitize_lora_filename(filename or Path(repo_file).name)
            resolve_url = (
                f"https://huggingface.co/{repo_id}/resolve/"
                f"{urllib.parse.quote(revision or url_rev, safe='')}/"
                f"{urllib.parse.quote(repo_file, safe='/')}"
            )
            return self._download_url(
                resolve_url,
                target_name=target_name,
                token=token or os.environ.get("HF_TOKEN"),
                on_progress=on_progress,
                progress_range=progress_range,
                source_label=f"HF:{repo_id}",
            )

        # Case 4: Direct HTTPS URL (Civitai, R2, S3, custom mirror, etc.)
        if raw.startswith(("https://", "http://")):
            parsed = urllib.parse.urlparse(raw)
            if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost"}:
                raise ValueError("出于安全要求，外部 LoRA 下载链接必须使用 HTTPS 协议。")
            guessed_name = filename or Path(urllib.parse.unquote(parsed.path)).name
            if not guessed_name or not guessed_name.lower().endswith(".safetensors"):
                url_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
                guessed_name = filename or f"remote_lora_{url_hash}.safetensors"
            target_name = sanitize_lora_filename(guessed_name)
            return self._download_url(
                raw,
                target_name=target_name,
                token=token,
                on_progress=on_progress,
                progress_range=progress_range,
                source_label=parsed.hostname or "HTTPS",
            )

        # Case 5: Hugging Face repo shorthand (`owner/repo` or `owner/repo::sub/file.safetensors` or `owner/repo/file.safetensors`)
        repo_id, repo_file = self._parse_hf_shorthand(raw, explicit_filename=filename, revision=revision or "main", token=token)
        rev = (revision or "main").strip()
        target_name = sanitize_lora_filename(filename or Path(repo_file).name)
        resolve_url = (
            f"https://huggingface.co/{repo_id}/resolve/"
            f"{urllib.parse.quote(rev, safe='')}/"
            f"{urllib.parse.quote(repo_file, safe='/')}"
        )
        return self._download_url(
            resolve_url,
            target_name=target_name,
            token=token or os.environ.get("HF_TOKEN"),
            on_progress=on_progress,
            progress_range=progress_range,
            source_label=f"HF:{repo_id}",
        )

    def _parse_hf_shorthand(
        self,
        raw: str,
        explicit_filename: Optional[str],
        revision: str,
        token: Optional[str],
    ) -> Tuple[str, str]:
        if "::" in raw:
            repo_part, file_part = raw.split("::", 1)
            return repo_part.strip("/ "), file_part.strip("/ ")

        parts = [p for p in raw.strip("/ ").split("/") if p]
        if len(parts) < 2:
            raise ValueError(
                f"无法识别的 LoRA 来源 '{raw}'。请输入 Hugging Face 仓库（owner/repo）或 HTTPS 下载直链。"
            )
        repo_id = f"{parts[0]}/{parts[1]}"
        if len(parts) > 2:
            return repo_id, "/".join(parts[2:])
        if explicit_filename and explicit_filename.lower().endswith(".safetensors"):
            # Check if explicit_filename exists in repo or use it directly
            return repo_id, explicit_filename

        if self.mock_mode:
            stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", parts[1])
            return repo_id, f"{stem}.safetensors"

        # Query Hugging Face model API to auto-discover .safetensors files in repo
        api_url = f"https://huggingface.co/api/models/{repo_id}/revision/{urllib.parse.quote(revision, safe='')}"
        headers = {"User-Agent": "colab-studio-lora-loader/1.0", "Accept": "application/json"}
        eff_token = token or os.environ.get("HF_TOKEN")
        if eff_token:
            headers["Authorization"] = f"Bearer {eff_token}"
        req = urllib.request.Request(api_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                info = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ValueError(f"查询 Hugging Face 仓库 {repo_id} 失败 (HTTP {exc.code})，请确认仓库名或传入 Token。") from exc

        siblings = info.get("siblings") or []
        st_files = [
            str(s.get("rfilename"))
            for s in siblings
            if isinstance(s, dict) and str(s.get("rfilename") or "").lower().endswith(".safetensors")
        ]
        if not st_files:
            raise ValueError(f"仓库 {repo_id} 中未找到任何 .safetensors 权重文件。")
        if len(st_files) == 1:
            return repo_id, st_files[0]
        preview = "、".join(st_files[:6])
        raise ValueError(
            f"仓库 {repo_id} 包含多个 .safetensors 文件（{preview}），请使用 '{repo_id}::文件名.safetensors' 指定具体权重。"
        )

    def _download_curated(
        self,
        spec: CuratedLoraSpec,
        *,
        token: Optional[str],
        on_progress: Optional[ProgressFn],
        progress_range: Tuple[float, float],
    ) -> LoraCatalogEntry:
        resolve_url = (
            f"https://huggingface.co/{spec.repo_id}/resolve/"
            f"{spec.revision}/{urllib.parse.quote(spec.repo_filename, safe='/')}"
        )
        return self._download_url(
            resolve_url,
            target_name=spec.filename,
            expected_size=spec.expected_size,
            token=token or os.environ.get("HF_TOKEN"),
            on_progress=on_progress,
            progress_range=progress_range,
            source_label=spec.label,
        )

    def _download_url(
        self,
        url: str,
        *,
        target_name: str,
        expected_size: Optional[int] = None,
        token: Optional[str] = None,
        on_progress: Optional[ProgressFn] = None,
        progress_range: Tuple[float, float] = (0.04, 0.96),
        source_label: str = "远程权重",
    ) -> LoraCatalogEntry:
        p_start, p_end = progress_range
        dest = ensure_safe_path(self.loras_dir / target_name, stop_at=self.loras_dir)

        if self.mock_mode:
            if on_progress:
                on_progress((p_start + p_end) * 0.5, f"[Mock] 正在模拟拉取 LoRA：{target_name}...")
            time.sleep(0.35)
            write_mock_safetensors(dest, metadata={"source": url, "downloaded_at": datetime.now(timezone.utc).isoformat()})
            if on_progress:
                on_progress(p_end, f"[Mock] LoRA 就绪：{target_name}")
            return self._entry_for_file(dest)

        usage = shutil.disk_usage(self.loras_dir)
        need_bytes = (expected_size or (256 * 1024 * 1024)) + MIN_FREE_HEADROOM_BYTES
        if usage.free < need_bytes:
            raise RuntimeError(
                f"磁盘可用空间不足：当前剩余 {usage.free / 1024**3:.2f} GB，无法安全缓存 LoRA。"
            )

        headers = {"User-Agent": "colab-studio-lora-loader/1.0"}
        if token:
            headers["Authorization"] = f"Bearer {token.strip()}"

        tmp_path = ensure_safe_path(
            self.loras_dir / f".dl_{target_name}_{int(time.time() * 1000)}.part",
            stop_at=self.loras_dir,
        )
        req = urllib.request.Request(url, headers=headers)
        started = time.monotonic()
        try:
            if on_progress:
                on_progress(p_start, f"正在连接下载 {source_label} ({target_name})...")
            with urllib.request.urlopen(req, timeout=60) as resp:
                content_len_hdr = resp.headers.get("Content-Length")
                total_len = int(content_len_hdr) if content_len_hdr and content_len_hdr.isdigit() else (expected_size or 0)
                if total_len > MAX_LORA_UPLOAD_BYTES:
                    raise RuntimeError("远程 LoRA 文件超过 4GB 安全上限。")
                if total_len and usage.free < total_len + MIN_FREE_HEADROOM_BYTES:
                    raise RuntimeError(
                        f"磁盘空间不足：文件需 {total_len / 1024**3:.2f} GB，当前仅剩 {usage.free / 1024**3:.2f} GB。"
                    )

                downloaded = 0
                last_emit = 0.0
                with tmp_path.open("wb") as out:
                    while True:
                        chunk = resp.read(2 * 1024 * 1024)
                        if not chunk:
                            break
                        downloaded += len(chunk)
                        if downloaded > MAX_LORA_UPLOAD_BYTES:
                            raise RuntimeError("下载数据超过 4GB 上限，已中止。")
                        out.write(chunk)
                        now = time.monotonic()
                        if on_progress and (now - last_emit >= 0.35):
                            last_emit = now
                            speed_mb = (downloaded / (1024 * 1024)) / max(0.1, now - started)
                            if total_len > 0:
                                frac = min(1.0, downloaded / total_len)
                                prog = p_start + (p_end - p_start) * frac
                                on_progress(
                                    prog,
                                    f"正在下载 LoRA {target_name}：{downloaded / 1024**2:.1f}/{total_len / 1024**2:.1f} MB ({speed_mb:.1f} MB/s)",
                                )
                            else:
                                on_progress(
                                    min(p_end - 0.05, p_start + 0.3),
                                    f"正在下载 LoRA {target_name}：已接收 {downloaded / 1024**2:.1f} MB ({speed_mb:.1f} MB/s)",
                                )

            verify_safetensors_file(tmp_path, expected_size=expected_size)
            tmp_path.replace(dest)
            if on_progress:
                on_progress(p_end, f"LoRA 校验通过并已挂载：{target_name}")
            return self._entry_for_file(dest)
        except urllib.error.HTTPError as exc:
            if tmp_path.exists():
                tmp_path.unlink()
            hint = "（若为受限模型或需要登录的 Civitai 链接，请展开填写 API Token）" if exc.code in {401, 403} else ""
            raise RuntimeError(f"下载 LoRA 失败 (HTTP {exc.code}){hint}：{url}") from exc
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise

    def _entry_for_file(self, path: Path) -> LoraCatalogEntry:
        spec = self.curated_by_filename.get(path.name)
        if spec:
            return LoraCatalogEntry(
                id=spec.id,
                filename=spec.filename,
                label=spec.label,
                description=spec.description,
                installed=True,
                curated=True,
                size_bytes=path.stat().st_size,
                recommended_strength=spec.recommended_strength,
                trigger_words=list(spec.trigger_words),
                tags=list(spec.tags),
                source_hint=f"{spec.repo_id}@{spec.revision[:10]}",
            )
        return LoraCatalogEntry(
            id=f"local:{path.name}",
            filename=path.name,
            label=path.name[: -len(".safetensors")],
            description="本地上传或外部在线拉取的自定义 LoRA 权重",
            installed=True,
            curated=False,
            size_bytes=path.stat().st_size,
            recommended_strength=0.85,
            trigger_words=[],
            tags=["自定义"],
            source_hint="本地已缓存",
        )

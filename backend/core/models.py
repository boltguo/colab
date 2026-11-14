"""Shared Pydantic schemas for tasks, files, and system health."""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

TaskStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
TunnelMode = Literal["local", "quick", "custom"]


class GpuStats(BaseModel):
    available: bool = False
    name: str = "CPU / Unavailable"
    utilization_pct: Optional[float] = None
    vram_total_gib: float = 0.0
    vram_used_gib: float = 0.0
    vram_free_gib: float = 0.0
    vram_percent: float = 0.0
    torch_allocated_gib: Optional[float] = None
    torch_reserved_gib: Optional[float] = None
    temperature_c: Optional[float] = None
    power_draw_w: Optional[float] = None
    power_limit_w: Optional[float] = None
    bf16_supported: bool = False
    torch_version: str = ""
    cuda_version: str = ""


class HostStats(BaseModel):
    cpu_count: int = 1
    cpu_percent: float = 0.0
    load_avg_1m: Optional[float] = None
    ram_total_gib: float = 0.0
    ram_used_gib: float = 0.0
    ram_free_gib: float = 0.0
    ram_percent: float = 0.0
    disk_mount: str = "/"
    disk_total_gib: float = 0.0
    disk_used_gib: float = 0.0
    disk_free_gib: float = 0.0
    disk_percent: float = 0.0
    uptime_sec: int = 0


class QueueStats(BaseModel):
    running: int = 0
    queued: int = 0
    succeeded: int = 0
    failed: int = 0


class SystemStatusResponse(BaseModel):
    feature: str
    title: str
    subtitle: str = ""
    version: str = "0.1.0"
    engine: str
    auth_required: bool = False
    mock_mode: bool = False
    public_url: str = ""
    tunnel_mode: TunnelMode = "local"
    gpu: GpuStats
    host: HostStats = Field(default_factory=HostStats)
    queue: QueueStats


class UploadedFileResponse(BaseModel):
    file_id: str
    filename: str
    content_type: str
    size_bytes: int
    url: str
    created_at: str


class PresetItem(BaseModel):
    id: str
    label: str
    description: str = ""
    kind: Literal["audio", "image", "video"] = "audio"
    url: str
    filename: str


class GenericTaskCreateRequest(BaseModel):
    params: Dict[str, Any] = Field(default_factory=dict, description="模型任务参数字典")


class TaskResponse(BaseModel):
    task_id: str
    feature: str
    status: TaskStatus
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    stage: str = ""
    queue_position: int = 0
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    elapsed_sec: Optional[float] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TaskListResponse(BaseModel):
    items: List[TaskResponse]

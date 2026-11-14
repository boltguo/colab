"""Single-GPU FIFO asynchronous task queue with live WebSocket progress broadcast."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set
import uuid

from fastapi import HTTPException

from .models import QueueStats, TaskResponse, TaskStatus
from .security import ensure_safe_dir, ensure_safe_path

ProgressCallback = Callable[[float, str], None]
TaskExecutor = Callable[[Dict[str, Any], ProgressCallback], Dict[str, Any]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskManager:
    def __init__(
        self,
        feature: str,
        executor: TaskExecutor,
        data_dir: Path,
        max_history: int = 100,
    ) -> None:
        self.feature = feature
        self._executor = executor
        self._data_dir = ensure_safe_dir(data_dir)
        self._index_path = ensure_safe_path(self._data_dir / "tasks_index.json", stop_at=self._data_dir)
        self._max_history = max_history

        self._lock = threading.Lock()
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._order: List[str] = []
        self._pending_ids: List[str] = []
        self._work_queue: "queue.Queue[Optional[str]]" = queue.Queue()

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

        self._load_persisted_history()

    def _load_persisted_history(self) -> None:
        if not self._index_path.is_file():
            return
        try:
            raw = json.loads(self._index_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                for item in raw[-self._max_history :]:
                    if isinstance(item, dict) and "task_id" in item:
                        # Stale running/queued tasks from a previous process become failed
                        if item.get("status") in {"queued", "running"}:
                            item["status"] = "failed"
                            item["error"] = "服务重启，历史排队任务已中断。"
                            item["finished_at"] = _utc_now()
                        tid = str(item["task_id"])
                        self._tasks[tid] = item
                        self._order.append(tid)
        except Exception:
            pass

    def _persist_locked(self) -> None:
        try:
            items = [self._tasks[tid] for tid in self._order[-self._max_history :] if tid in self._tasks]
            tmp = ensure_safe_path(self._index_path.with_suffix(".tmp"), stop_at=self._data_dir)
            tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._index_path)
        except Exception:
            pass

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name=f"task-worker-{self.feature}",
            daemon=True,
        )
        self._worker_thread.start()

    def stop(self) -> None:
        self._running = False
        self._work_queue.put(None)
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=3.0)

    def submit(self, validated_params: Dict[str, Any]) -> TaskResponse:
        task_id = uuid.uuid4().hex[:16]
        now = _utc_now()
        record: Dict[str, Any] = {
            "task_id": task_id,
            "feature": self.feature,
            "status": "queued",
            "progress": 0.0,
            "stage": "排队等待 GPU 执行...",
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "elapsed_sec": None,
            "params": validated_params,
            "result": None,
            "error": None,
        }
        with self._lock:
            self._tasks[task_id] = record
            self._order.append(task_id)
            self._pending_ids.append(task_id)
            if len(self._order) > self._max_history * 2:
                evict = self._order[: -self._max_history]
                self._order = self._order[-self._max_history :]
                for old_id in evict:
                    if old_id not in self._pending_ids and self._tasks.get(old_id, {}).get("status") != "running":
                        self._tasks.pop(old_id, None)
            self._persist_locked()
            snapshot = self._build_response_locked(task_id)

        self._work_queue.put(task_id)
        self._notify_subscribers(task_id, snapshot)
        return snapshot

    def get(self, task_id: str) -> TaskResponse:
        with self._lock:
            if task_id not in self._tasks:
                raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
            return self._build_response_locked(task_id)

    def list_recent(self, limit: int = 30) -> List[TaskResponse]:
        with self._lock:
            recent_ids = list(reversed(self._order[-limit:]))
            return [self._build_response_locked(tid) for tid in recent_ids if tid in self._tasks]

    def cancel(self, task_id: str) -> TaskResponse:
        with self._lock:
            rec = self._tasks.get(task_id)
            if not rec:
                raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
            if rec["status"] == "queued":
                rec["status"] = "cancelled"
                rec["stage"] = "已取消排队"
                rec["finished_at"] = _utc_now()
                if task_id in self._pending_ids:
                    self._pending_ids.remove(task_id)
                self._persist_locked()
            elif rec["status"] == "running":
                raise HTTPException(status_code=409, detail="任务正在 GPU 上执行中，暂不支持中途强杀。")
            snapshot = self._build_response_locked(task_id)
        self._notify_subscribers(task_id, snapshot)
        return snapshot

    def queue_stats(self) -> QueueStats:
        with self._lock:
            running = sum(1 for r in self._tasks.values() if r["status"] == "running")
            queued = len(self._pending_ids)
            succeeded = sum(1 for r in self._tasks.values() if r["status"] == "succeeded")
            failed = sum(1 for r in self._tasks.values() if r["status"] == "failed")
            return QueueStats(running=running, queued=queued, succeeded=succeeded, failed=failed)

    def subscribe(self, task_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subscribers.setdefault(task_id, set()).add(q)
        return q

    def unsubscribe(self, task_id: str, q: asyncio.Queue) -> None:
        subs = self._subscribers.get(task_id)
        if subs:
            subs.discard(q)
            if not subs:
                self._subscribers.pop(task_id, None)

    def _build_response_locked(self, task_id: str) -> TaskResponse:
        rec = self._tasks[task_id]
        pos = (self._pending_ids.index(task_id) + 1) if task_id in self._pending_ids else 0
        return TaskResponse(
            task_id=rec["task_id"],
            feature=rec["feature"],
            status=rec["status"],
            progress=float(rec.get("progress") or 0.0),
            stage=str(rec.get("stage") or ""),
            queue_position=pos,
            created_at=rec["created_at"],
            started_at=rec.get("started_at"),
            finished_at=rec.get("finished_at"),
            elapsed_sec=rec.get("elapsed_sec"),
            params=rec.get("params") or {},
            result=rec.get("result"),
            error=rec.get("error"),
        )

    def _notify_subscribers(self, task_id: str, snapshot: TaskResponse) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return

        payload = snapshot.model_dump()

        def _push() -> None:
            for q in list(self._subscribers.get(task_id, ())):
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    pass

        try:
            loop.call_soon_threadsafe(_push)
        except RuntimeError:
            pass

    def _update_task(
        self,
        task_id: str,
        *,
        status: Optional[TaskStatus] = None,
        progress: Optional[float] = None,
        stage: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
        elapsed_sec: Optional[float] = None,
        persist: bool = False,
    ) -> None:
        with self._lock:
            rec = self._tasks.get(task_id)
            if not rec:
                return
            if status is not None:
                rec["status"] = status
            if progress is not None:
                rec["progress"] = max(0.0, min(1.0, float(progress)))
            if stage is not None:
                rec["stage"] = stage
            if result is not None:
                rec["result"] = result
            if error is not None:
                rec["error"] = error
            if started_at is not None:
                rec["started_at"] = started_at
            if finished_at is not None:
                rec["finished_at"] = finished_at
            if elapsed_sec is not None:
                rec["elapsed_sec"] = round(elapsed_sec, 2)
            if persist:
                self._persist_locked()
            snapshot = self._build_response_locked(task_id)

        self._notify_subscribers(task_id, snapshot)

    def _worker_loop(self) -> None:
        while self._running:
            task_id = self._work_queue.get()
            if task_id is None:
                break

            with self._lock:
                rec = self._tasks.get(task_id)
                if not rec or rec["status"] != "queued":
                    if task_id in self._pending_ids:
                        self._pending_ids.remove(task_id)
                    continue
                if task_id in self._pending_ids:
                    self._pending_ids.remove(task_id)
                params = dict(rec["params"])

            t0 = time.monotonic()
            self._update_task(
                task_id,
                status="running",
                progress=0.02,
                stage="准备加载模型与推理环境...",
                started_at=_utc_now(),
                persist=True,
            )

            def on_progress(val: float, desc: str = "") -> None:
                clamped = max(0.02, min(0.99, float(val)))
                self._update_task(task_id, progress=clamped, stage=desc or "模型推理中...")

            try:
                result = self._executor(params, on_progress)
                elapsed = time.monotonic() - t0
                self._update_task(
                    task_id,
                    status="succeeded",
                    progress=1.0,
                    stage="生成完成",
                    result=result,
                    finished_at=_utc_now(),
                    elapsed_sec=elapsed,
                    persist=True,
                )
            except Exception as exc:
                elapsed = time.monotonic() - t0
                self._update_task(
                    task_id,
                    status="failed",
                    stage="执行失败",
                    error=str(exc),
                    finished_at=_utc_now(),
                    elapsed_sec=elapsed,
                    persist=True,
                )

"""Queue cancellation and restart recovery regressions without an inference engine."""
import asyncio
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from backend.core.config import _resolve_dist_dir
from backend.core.task_manager import TaskManager


class TaskManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_dir = Path(self.tmp.name)
        self.loop = asyncio.new_event_loop()
        self.addCleanup(self.loop.close)

    def manager(self, executor):
        manager = TaskManager("queue-test", executor, self.data_dir)
        self.addCleanup(manager.stop)
        return manager

    def observe_completion(self, manager):
        events = {}
        notify = manager._notify_subscribers

        def observer(task_id, snapshot):
            notify(task_id, snapshot)
            if snapshot.status in {"succeeded", "failed", "cancelled"}:
                events.setdefault(task_id, threading.Event()).set()

        manager._notify_subscribers = observer

        def wait(task_id):
            self.assertTrue(events.setdefault(task_id, threading.Event()).wait(2), "Task did not finish")
            return manager.get(task_id)

        return wait

    def test_cancelled_queued_task_never_reaches_executor(self):
        running = threading.Event()
        release = threading.Event()
        executed = []

        def execute(params, progress):
            executed.append(params["name"])
            if params["name"] == "first":
                running.set()
                release.wait(2)
            return {"name": params["name"]}

        manager = self.manager(execute)
        self.addCleanup(release.set)
        wait = self.observe_completion(manager)
        manager.start(self.loop)
        first = manager.submit({"name": "first"})
        self.assertTrue(running.wait(2))
        cancelled = manager.submit({"name": "cancelled"})
        third = manager.submit({"name": "third"})
        self.assertEqual(manager.cancel(cancelled.task_id).status, "cancelled")
        self.assertEqual(manager.get(third.task_id).queue_position, 1)
        release.set()
        self.assertEqual(wait(first.task_id).status, "succeeded")
        self.assertEqual(wait(third.task_id).status, "succeeded")
        self.assertEqual(executed, ["first", "third"])
        self.assertEqual(manager.get(cancelled.task_id).status, "cancelled")

    def test_cancel_cannot_succeed_after_worker_claims_task(self):
        # Suspend between claiming work and calling the model. Cancellation must
        # observe "running" even if the worker is descheduled in this interval.
        claimed = threading.Event()
        release = threading.Event()
        first_clock_read = True

        def monotonic():
            nonlocal first_clock_read
            if first_clock_read:
                first_clock_read = False
                claimed.set()
                release.wait(2)
            return time.monotonic()

        executor = Mock(return_value={"output": "complete"})
        manager = self.manager(executor)
        self.addCleanup(release.set)
        wait = self.observe_completion(manager)
        task = manager.submit({"seed": 42})
        with patch("backend.core.task_manager.time", SimpleNamespace(monotonic=monotonic)):
            manager.start(self.loop)
            self.assertTrue(claimed.wait(2))
            with self.assertRaises(HTTPException) as error:
                manager.cancel(task.task_id)
            self.assertEqual(error.exception.status_code, 409)
            self.assertEqual(manager.get(task.task_id).status, "running")
            self.assertEqual(manager.queue_stats().queued, 0)
            release.set()
            self.assertEqual(wait(task.task_id).status, "succeeded")
        executor.assert_called_once()

    def test_failure_does_not_block_the_next_task(self):
        def execute(params, progress):
            if params["fail"]:
                raise RuntimeError("decoder rejected input")
            progress(0.5, "working")
            return {"output": "next-result"}

        manager = self.manager(execute)
        wait = self.observe_completion(manager)
        failed = manager.submit({"fail": True})
        succeeded = manager.submit({"fail": False})
        manager.start(self.loop)
        self.assertEqual(wait(failed.task_id).error, "decoder rejected input")
        result = wait(succeeded.task_id)
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.progress, 1)
        self.assertEqual(result.result, {"output": "next-result"})

    def test_completed_history_restores_results_and_full_parameters(self):
        params = {"seed": 123, "mode": "image", "layers": [{"strength": 0.5}], "input": "source.png"}
        result = {"image_url": "/api/v1/outputs/result.png", "width": 1024, "used_seed": 123}
        manager = self.manager(lambda *_: result)
        wait = self.observe_completion(manager)
        manager.start(self.loop)
        task = manager.submit(params)
        wait(task.task_id)
        manager.stop()

        restored = self.manager(Mock())
        records = restored.list_recent(100)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].task_id, task.task_id)
        self.assertEqual(records[0].params, params)
        self.assertEqual(records[0].result, result)
        self.assertEqual(records[0].status, "succeeded")
        self.assertIsNotNone(records[0].finished_at)
        self.assertEqual(restored.queue_stats().queued, 0)

    def test_restart_marks_interrupted_work_failed_without_reexecuting_it(self):
        entered = threading.Event()
        release = threading.Event()

        def execute(*_):
            entered.set()
            release.wait(2)
            return {"result": "unused"}

        original = self.manager(execute)
        self.addCleanup(release.set)
        original.start(self.loop)
        running = original.submit({"name": "running"})
        self.assertTrue(entered.wait(2))
        queued = original.submit({"name": "queued"})
        cancelled = original.submit({"name": "cancelled"})
        original.cancel(cancelled.task_id)

        executor = Mock()
        restored = self.manager(executor)
        for task in (running, queued):
            self.assertEqual(restored.get(task.task_id).status, "failed")
            self.assertIn("服务重启", restored.get(task.task_id).error)
        self.assertEqual(restored.get(cancelled.task_id).status, "cancelled")
        self.assertEqual(restored.queue_stats().running, 0)
        self.assertEqual(restored.queue_stats().queued, 0)
        restored.start(self.loop)
        restored.stop()
        executor.assert_not_called()
        release.set()

    def test_monorepo_build_output_is_resolved_by_feature(self):
        dist = self.data_dir / "frontend" / "dist" / "seedvr2"
        dist.mkdir(parents=True)
        (dist / "index.html").write_text("<!doctype html><title>SeedVR2</title>")
        with patch.dict("os.environ", {"COLAB_DIST_DIR": ""}):
            self.assertEqual(_resolve_dist_dir("seedvr2", self.data_dir), dist)
            self.assertIsNone(_resolve_dist_dir("minimax-h3", self.data_dir))


if __name__ == "__main__":
    unittest.main()

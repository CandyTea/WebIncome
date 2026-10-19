"""Watch one explicitly configured local workbook without modifying it."""
from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from tools.export_sheet2 import ExportError, extract_bytes


class SyncRejected(RuntimeError):
    """The remote site refused this workbook; wait for the next save."""


class RetryableSyncError(RuntimeError):
    """A temporary failure; retry the same saved workbook later."""


class LocalWorkbookSync:
    def __init__(self, path, save_snapshot, existing_hash=None, stable_seconds=1.5, retry_seconds=10):
        self.path = Path(path).resolve()
        self.save_snapshot = save_snapshot
        self.stable_seconds = stable_seconds
        self.retry_seconds = retry_seconds
        self._source_hash = existing_hash
        self._candidate = None
        self._candidate_since = 0.0
        self._processed = None
        self._next_retry = 0.0
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._status = {"enabled": True, "fileName": self.path.name, "state": "waiting", "message": "正在检查本地文件…", "lastSyncedAt": None}

    def status(self):
        with self._lock:
            return dict(self._status)

    def note_external_update(self):
        # A manual upload wins until this watched file is saved again.
        self._source_hash = None

    def _update(self, **values):
        with self._lock:
            self._status.update(values)

    @staticmethod
    def _signature(stat):
        return stat.st_mtime_ns, stat.st_size, stat.st_ino

    def check_once(self, now=None):
        now = time.monotonic() if now is None else now
        if now < self._next_retry:
            return
        try:
            signature = self._signature(self.path.stat())
            if signature == self._processed:
                return
            if signature != self._candidate:
                self._candidate, self._candidate_since = signature, now
                self._update(state="waiting", message="检测到保存，等待文件写入完成…")
                return
            if now - self._candidate_since < self.stable_seconds:
                return
            if signature[1] > 10 * 1024 * 1024:
                raise ExportError("Excel 文件不能超过 10 MB。")
            contents = self.path.read_bytes()
            if self._signature(self.path.stat()) != signature:
                self._candidate = None
                return
            digest = hashlib.sha256(contents).hexdigest()
            if digest != self._source_hash:
                self._update(state="importing", message="正在读取并核验本地 Excel…")
                payload, audit = extract_bytes(contents)
                # Saving can replace the file while parsing; wait for the new
                # version instead of publishing an intermediate save.
                if self._signature(self.path.stat()) != signature:
                    self._candidate = None
                    return
                self.save_snapshot(payload, audit, {"kind": "local", "fileName": self.path.name}, contents)
                self._source_hash = digest
            self._processed = signature
            self._update(state="synced", message="已同步。保存 Excel 后会自动更新。", lastSyncedAt=datetime.now(timezone.utc).isoformat())
        except RetryableSyncError as error:
            # Network or server failures should retry the same saved file
            # without waiting for another save.
            self._next_retry = now + self.retry_seconds
            self._update(state="error", message=f"同步未完成：{error} 将自动重试。已有网页数据已保留。")
        except OSError:
            self._candidate = None
            self._processed = None
            self._next_retry = now + 3
            self._update(state="error", message="暂时无法读取文件，将自动重试。已有网页数据已保留。")
        except Exception as error:
            # Invalid saved files are retried after the next save. Valid data
            # remains untouched, including when Excel clears formula caches.
            self._processed = self._candidate
            message = str(error) if isinstance(error, (ExportError, SyncRejected)) else "无法读取此 Excel，请在 Excel/WPS 中计算并重新保存。"
            self._update(state="error", message=f"同步未完成：{message} 原有数据已保留。")

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="local-workbook-sync", daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            self.check_once()
            self._stop.wait(1)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

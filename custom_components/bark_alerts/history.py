"""Optional local bark audio archive, entirely separate from RF dispatch."""

from __future__ import annotations

import asyncio
import json
import math
import re
import time
from collections import deque
from pathlib import Path
from uuid import uuid4

from .recording_api import (
    POST_SECONDS,
    PRE_SECONDS,
    FrigateRecordingClient,
    HistoryError,
)

LIMIT = 25
MAX_AUDIO = 400_000
SETTLE_SECONDS = 15
SAFE_ID = re.compile(r"^[a-f0-9]{32}$")


async def extract_audio(source: Path, target: Path, binary: str = "ffmpeg") -> None:
    """Decode only local input into bounded mono PCM; never invoke a shell."""
    try:
        process = await asyncio.create_subprocess_exec(
            binary,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-t",
            str(PRE_SECONDS + POST_SECONDS),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-fs",
            str(MAX_AUDIO),
            "-f",
            "wav",
            str(target),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError:
        raise HistoryError("ffmpeg_unavailable") from None
    try:
        async with asyncio.timeout(30):
            result = await process.wait()
        if result:
            raise HistoryError("audio_unavailable")
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


class BarkHistory:
    """Keep the latest 25 episodes, including explicit capture failures."""

    def __init__(self, hass, entry, notify, *, fetch=None, extract=None):
        self.hass, self.entry, self.notify = hass, entry, notify
        self.folder = Path(
            hass.config.path(".storage", "bark_alerts_history", entry.entry_id)
        )
        self.items: list[dict] = []
        self.pending = deque()
        self.task = None
        self._save_lock = asyncio.Lock()
        self.closed = False
        self.status = "idle"
        self.fetch = fetch or FrigateRecordingClient().download
        self.extract = extract or extract_audio

    async def _io(self, func, *args):
        # Do not let reload/clear race an executor write that outlives cancellation.
        task = self.hass.async_add_executor_job(func, *args)
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    def _load(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        index = self.folder / "index.json"
        try:
            if index.stat().st_size > 100_000:
                return []
            data = json.loads(index.read_text(encoding="utf-8"))
        except OSError, ValueError:
            return []
        if not isinstance(data, list):
            return []
        result = []
        for row in data[:LIMIT]:
            if not isinstance(row, dict) or not SAFE_ID.fullmatch(
                str(row.get("id", ""))
            ):
                continue
            if (
                not isinstance(row.get("timestamp"), (int, float))
                or not math.isfinite(row["timestamp"])
                or not 0 < row["timestamp"] < 32_503_680_000
                or not isinstance(row.get("status"), str)
                or not isinstance(row.get("outcome"), str)
            ):
                continue
            if row.get("status") == "pending":
                row["status"] = "interrupted"
            if row.get("status") == "ready":
                path = self.folder / f"{row['id']}.wav"
                if (
                    path.is_symlink()
                    or not path.is_file()
                    or not 44 < path.stat().st_size <= MAX_AUDIO
                ):
                    row["status"] = "audio_unavailable"
            result.append(row)
        return result

    def _persist(self, rows):
        self.folder.mkdir(parents=True, exist_ok=True)
        temp = self.folder / "index.tmp"
        temp.write_text(json.dumps(rows), encoding="utf-8")
        temp.replace(self.folder / "index.json")
        keep = {f"{row['id']}.wav" for row in rows if row["status"] == "ready"}
        for path in self.folder.glob("*.wav"):
            if path.name not in keep and SAFE_ID.fullmatch(path.stem):
                path.unlink(missing_ok=True)

    async def initialize(self):
        try:
            self.items = await self._io(self._load)
            await self.save()
            # Leftovers from an interrupted conversion are never playable.
            await self._io(self._cleanup_temp)
        except OSError:
            self.status = "storage_error"

    def _cleanup_temp(self):
        for name in ("capture.mp4", "capture.wav"):
            (self.folder / name).unlink(missing_ok=True)

    async def save(self):
        async with self._save_lock:
            while True:
                snapshot = [dict(row) for row in self.items]
                await self._io(self._persist, snapshot)
                if snapshot == self.items:
                    break

    def add(self, timestamp, camera_id=None):
        if self.closed:
            return None
        row = {
            "id": uuid4().hex,
            "timestamp": timestamp,
            "outcome": "pending",
            "status": "pending",
        }
        if camera_id is not None:
            row["camera_id"] = camera_id
        self.items.insert(0, row)
        del self.items[LIMIT:]
        self.pending.append(row)
        while len(self.pending) > LIMIT:
            self.pending.popleft()
        if self.task is None or self.task.done():
            self.task = self.hass.async_create_background_task(
                self._worker(), "Bark audio history"
            )
        self.notify()
        return row["id"]

    def outcome(self, item_id, outcome):
        for row in self.items:
            if row["id"] == item_id:
                row["outcome"] = outcome
                if not self.closed and (self.task is None or self.task.done()):
                    self.task = self.hass.async_create_background_task(
                        self._worker(), "Save bark outcome"
                    )
                return

    async def _worker(self):
        try:
            while self.pending and not self.closed:
                row = self.pending.popleft()
                if row not in self.items:
                    continue
                await self.save()
                await asyncio.sleep(
                    max(
                        0,
                        row["timestamp"] + POST_SECONDS + SETTLE_SECONDS - time.time(),
                    )
                )
                if row not in self.items:
                    continue
                try:
                    if "camera_id" in row:
                        content = await self.fetch(
                            self.hass, self.entry, row["timestamp"], row["camera_id"]
                        )
                    else:
                        content = await self.fetch(
                            self.hass, self.entry, row["timestamp"]
                        )
                    source, target = (
                        self.folder / "capture.mp4",
                        self.folder / "capture.wav",
                    )
                    await self._io(source.write_bytes, content)
                    await self.extract(source, target, "ffmpeg")
                    size = (await self._io(target.stat)).st_size
                    if not 44 < size <= MAX_AUDIO:
                        raise HistoryError("audio_unavailable")
                    if row in self.items:
                        await self._io(target.replace, self.folder / f"{row['id']}.wav")
                        row["status"] = "ready"
                except HistoryError as err:
                    row["status"] = str(err)
                except Exception:
                    row["status"] = "capture_failed"
                finally:
                    await self._io(self._cleanup_temp)
                self.status = row["status"]
                await self.save()
                self.notify()
            await self.save()
            self.notify()
        except OSError:
            self.status = "storage_error"
            self.notify()

    def stop(self):
        self.closed = True
        if self.task:
            self.task.cancel()

    async def close(self):
        self.stop()
        if self.task:
            await asyncio.gather(self.task, return_exceptions=True)
        for row in self.items:
            if row["status"] == "pending":
                row["status"] = "interrupted"
        self.pending.clear()
        try:
            await self.save()
            await self._io(self._cleanup_temp)
        except OSError:
            self.status = "storage_error"

    async def clear(self):
        await self.close()
        self.items.clear()
        self.closed = False
        self.status = "idle"
        await self.save()
        self.notify()

    def clip_path(self, item_id):
        if not SAFE_ID.fullmatch(item_id):
            return None
        if not any(
            row["id"] == item_id and row["status"] == "ready" for row in self.items
        ):
            return None
        return self.folder / f"{item_id}.wav"

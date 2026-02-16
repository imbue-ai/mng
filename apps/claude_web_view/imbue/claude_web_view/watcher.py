import asyncio
from pathlib import Path
from typing import Any

from watchfiles import Change
from watchfiles import awatch

from .parser import TranscriptParser


class TranscriptWatcher:
    """Watches transcript file for changes and notifies subscribers."""

    def __init__(self, transcript_path: Path, parser: TranscriptParser):
        self.transcript_path = transcript_path
        self.parser = parser
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self._watch_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    def subscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Subscribe to updates."""
        self._subscribers.append(queue)

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Unsubscribe from updates."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    async def _broadcast(self, event: dict[str, Any]) -> None:
        """Broadcast event to all subscribers."""
        for queue in self._subscribers:
            try:
                await queue.put(event)
            except Exception:
                pass  # Subscriber disconnected

    async def _watch_loop(self) -> None:
        """Main watch loop."""
        try:
            async for changes in awatch(
                self.transcript_path,
                stop_event=self._stop_event,
            ):
                for change_type, _path in changes:
                    if change_type == Change.modified:
                        # Parse new content
                        new_messages = self.parser.parse_updates()

                        for message in new_messages:
                            await self._broadcast(
                                {
                                    "type": "message",
                                    "message": message.model_dump(),
                                }
                            )
        except asyncio.CancelledError:
            pass

    async def start(self) -> None:
        """Start watching."""
        self._stop_event.clear()
        self._watch_task = asyncio.create_task(self._watch_loop())

    async def stop(self) -> None:
        """Stop watching."""
        self._stop_event.set()
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass

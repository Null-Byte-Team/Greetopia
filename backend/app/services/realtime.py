"""Live updates over WebSocket. Producers (MQTT worker thread, request threads) call publish(); it is thread-safe and a no-op
until the first client connects. Each client has a bounded queue; on overflow the client receives {"type":"resync"} and must
re-fetch /plants/{id}/overview. Clients also re-fetch after every reconnect (state is never reconstructed from events alone)."""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone

MAX_CLIENTS = 100
QUEUE_SIZE = 200

_loop: asyncio.AbstractEventLoop | None = None
_clients: set["Client"] = set()
_seq = 0
_lock = threading.Lock()


class Client:
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_SIZE)


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def current_seq() -> int:
    return _seq


def client_count() -> int:
    return len(_clients)


def add_client(c: Client) -> bool:
    if len(_clients) >= MAX_CLIENTS:
        return False
    _clients.add(c)
    return True


def remove_client(c: Client) -> None:
    _clients.discard(c)


def _fanout(msg: dict) -> None:  # runs on the event loop
    for c in list(_clients):
        try:
            c.queue.put_nowait(msg)
        except asyncio.QueueFull:
            while not c.queue.empty():
                c.queue.get_nowait()
            c.queue.put_nowait({"type": "resync", "seq": msg["seq"]})


def publish(kind: str, plant_id: str | None, data: dict) -> None:
    global _seq
    if _loop is None or not _clients:
        return
    with _lock:
        _seq += 1
        msg = {"type": kind, "plant_id": plant_id, "seq": _seq, "at": datetime.now(timezone.utc).isoformat(), "data": data}
    try:
        _loop.call_soon_threadsafe(_fanout, msg)
    except RuntimeError:  # loop closed during shutdown
        pass

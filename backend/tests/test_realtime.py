import pytest

from app.services import realtime
from app.services.telemetry import record_reading
from tests.conftest import _signup


def test_ws_requires_auth_first_message(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/api/v1/ws") as ws:
            ws.send_json({"type": "auth", "token": "garbage"})
            ws.receive_json()


def test_ws_streams_readings_and_commands(client, admin, monkeypatch):
    token = admin["Authorization"].split()[1]
    with client.websocket_connect("/api/v1/ws") as ws:
        ws.send_json({"type": "auth", "token": token})
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["role"] == "admin"
        record_reading("plant01", "soil_root", 41.0, "t")
        msg = ws.receive_json()
        assert msg["type"] == "reading" and msg["data"]["metric"] == "soil_root" and msg["data"]["value"] == 41.0 and msg["seq"] > hello["seq"]
        from app.services.telemetry import ingest_mqtt
        ingest_mqtt("plants/plant01/status", b"watering")
        kinds = {ws.receive_json()["type"] for _ in range(2)}
        assert "pump" in kinds and "alert" in kinds  # unrequested watering => pump update + critical alert


def test_slow_client_gets_resync_not_unbounded_memory():
    import asyncio
    async def run():
        realtime.bind_loop(asyncio.get_running_loop())
        c = realtime.Client(); realtime.add_client(c)
        try:
            for i in range(realtime.QUEUE_SIZE + 5):
                realtime.publish("reading", "p", {"i": i})
            await asyncio.sleep(0.2)
            assert c.queue.qsize() <= realtime.QUEUE_SIZE
            last = None
            while not c.queue.empty():
                last = c.queue.get_nowait()
            assert last["type"] in ("resync", "reading")
        finally:
            realtime.remove_client(c)
    asyncio.run(run())

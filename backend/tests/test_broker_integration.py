"""Real MQTT round trip against a local Mosquitto with the project's ACL model. Skipped if mosquitto is not installed."""
import os
import shutil
import socket
import subprocess
import time

import pytest

pytestmark = pytest.mark.skipif(not shutil.which("mosquitto") or not shutil.which("mosquitto_passwd"), reason="mosquitto not installed")


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def wait_for(cond, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.1)
    return False


@pytest.fixture()
def broker():
    import tempfile, pathlib
    tmp_path = pathlib.Path(tempfile.mkdtemp(prefix="mq-"))
    os.chmod(tmp_path, 0o755)  # mosquitto drops root privileges and must traverse this directory
    port = free_port()
    pw = tmp_path / "passwd"
    for user in ("greetopia_backend", "plant01", "evil"):
        subprocess.run(["mosquitto_passwd", "-b", "-c" if not pw.exists() else "-b", str(pw), user, f"{user}-pw"], check=True, capture_output=True)
    os.chmod(pw, 0o644)  # mosquitto drops root privileges and must be able to read it
    (tmp_path / "acl").write_text("""user greetopia_backend
topic read plants/#
topic write plants/+/water
user plant01
topic write plants/plant01/soil/+
topic write plants/plant01/temp
topic write plants/plant01/humidity
topic write plants/plant01/status
topic write plants/plant01/availability
topic write plants/plant01/ack
topic write plants/plant01/fault
topic read plants/plant01/water
user evil
topic write plants/plant01/temp
""")
    (tmp_path / "m.conf").write_text(f"listener {port} 127.0.0.1\nallow_anonymous false\npassword_file {pw}\nacl_file {tmp_path / 'acl'}\npersistence false\n")
    proc = subprocess.Popen(["mosquitto", "-c", str(tmp_path / "m.conf")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert wait_for(lambda: socket.socket().connect_ex(("127.0.0.1", port)) == 0, 5)
    yield port
    proc.terminate(); proc.wait(5)


def client(port, user, will=None):
    import paho.mqtt.client as mqtt
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"t-{user}-{time.time()}")
    c.username_pw_set(user, f"{user}-pw")
    if will:
        c.will_set(*will)
    c.connect("127.0.0.1", port, 20)
    c.loop_start()
    return c


def test_full_round_trip_with_acl(env, broker, monkeypatch):
    from app.core.config import settings
    from app.db.database import db_session
    from app.services import device_state, mqtt_service
    from app.services.irrigation import request_watering
    from app.services.telemetry import latest_readings

    monkeypatch.setattr(settings, "mqtt_enabled", True)
    monkeypatch.setattr(settings, "mqtt_host", "127.0.0.1")
    monkeypatch.setattr(settings, "mqtt_port", broker)
    monkeypatch.setattr(settings, "mqtt_username", "greetopia_backend")
    monkeypatch.setattr(settings, "mqtt_password", "greetopia_backend-pw")
    mqtt_service.start_mqtt()
    assert wait_for(lambda: mqtt_service.mqtt_status()["connected"]), "backend did not connect"

    received = []
    node = client(broker, "plant01", will=("plants/plant01/availability", "offline", 1, True))
    node.on_message = lambda c, u, m: received.append((m.topic, m.payload.decode()))
    node.subscribe("plants/plant01/water")
    time.sleep(0.5)
    try:
        # 1) telemetry in the exact firmware formats reaches the DB
        for t, p in [("soil/surface", "41"), ("soil/mid", "42"), ("soil/root", "43"), ("temp", "24.50"), ("humidity", "55.20"), ("availability", "online")]:
            node.publish(f"plants/plant01/{t}", p, qos=1)
        assert wait_for(lambda: latest_readings("plant01").get("soil_root", {}).get("value") == 43)
        assert latest_readings("plant01")["temperature_c"]["value"] == 24.5
        # 2) malformed message from an authorised node is quarantined, not stored
        node.publish("plants/plant01/temp", "999", qos=1)
        assert wait_for(lambda: mqtt_service._stats["quarantined"] >= 1)
        # 3) backend command arrives as exactly ON:5 and ACL lets the node read it
        res = request_watering("plant01", 5, "manual", "it@test", "integration")
        assert res["published"] is True
        assert wait_for(lambda: ("plants/plant01/water", "ON:5") in received)
        # 4) node answers: ack -> watering -> idle reconciles the event to confirmed
        node.publish("plants/plant01/ack", "accepted:5", qos=1)
        node.publish("plants/plant01/status", "watering", qos=1)
        node.publish("plants/plant01/status", "idle", qos=1)
        def status():
            with db_session() as db:
                return db.execute("SELECT status FROM irrigation_events ORDER BY id DESC LIMIT 1").fetchone()["status"]
        assert wait_for(lambda: status() == "confirmed")
        # 5) ACL: a non-backend identity cannot publish pump commands
        evil = client(broker, "evil")
        received.clear()
        evil.publish("plants/plant01/water", "ON:15", qos=1)
        time.sleep(1.5)
        assert ("plants/plant01/water", "ON:15") not in received
        evil.loop_stop(); evil.disconnect()
        # 6) ungraceful node loss -> broker last-will -> offline
        node._sock.close()
        assert wait_for(lambda: device_state.device_summary("plant01")["state"] == "offline", 15)
    finally:
        mqtt_service.stop_mqtt()
        try:
            node.loop_stop()
        except Exception:
            pass

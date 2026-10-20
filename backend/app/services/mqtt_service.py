"""MQTT adapter. All broker-specific logic lives here.

- Messages are placed on a bounded queue and processed by a worker thread, so slow DB writes never block
  the network loop; overflow is counted, never silently ignored.
- Malformed messages are quarantined with a reason code instead of vanishing into a log line.
- Retained messages are ignored for telemetry (stale by definition) but honoured for availability (last-will).
- Public test brokers are refused unless MQTT_DEV_PUBLIC_BROKER=true.
"""
import logging
import queue
import ssl
import threading
from datetime import datetime, timezone

from app.core.config import FIRMWARE_MAX_PUMP_S, settings
from app.services.telemetry import IngestError, ingest_mqtt, quarantine

log = logging.getLogger(__name__)

PUBLIC_BROKERS = ("broker.hivemq.com", "test.mosquitto.org", "broker.emqx.io", "mqtt.eclipseprojects.io", "public.mqtthq.com")
SUBSCRIPTIONS = ("plants/+/soil/+", "plants/+/temp", "plants/+/humidity", "plants/+/status",
                 "plants/+/availability", "plants/+/ack", "plants/+/fault", "plants/+/leaf_wetness")

_client = None
_connected = False
_last_connected_at = None
_last_error = None
_queue: "queue.Queue | None" = None
_worker: "threading.Thread | None" = None
_stats = {"received": 0, "processed": 0, "quarantined": 0, "dropped_queue_full": 0, "ignored_retained": 0}


def mqtt_status(include_details: bool = False):
    """Observable state. Details (errors, counters) are only for authenticated callers."""
    status = {"enabled": bool(settings.mqtt_enabled), "connected": bool(_client and _client.is_connected() and _connected)}
    if include_details:
        status.update({"last_connected_at": _last_connected_at, "last_error": _last_error, "stats": dict(_stats),
                       "queue_depth": _queue.qsize() if _queue else 0})
    return status


def _is_public_broker(host: str) -> bool:
    return host.lower() in PUBLIC_BROKERS


def process_message(topic: str, payload: bytes, retain: bool = False) -> None:
    """Validate and persist one message. Never raises: failures are quarantined."""
    if retain and not topic.endswith("/availability"):
        _stats["ignored_retained"] += 1
        return
    try:
        ingest_mqtt(topic, payload)
        _stats["processed"] += 1
    except IngestError as exc:
        _stats["quarantined"] += 1
        log.warning("Quarantined MQTT message on %s: %s", topic[:80], exc.reason)
        try:
            quarantine(topic, payload, exc.reason)
        except Exception:
            log.exception("Could not write quarantine record")
    except Exception:
        _stats["quarantined"] += 1
        log.exception("Unexpected error while processing %s", topic[:80])


def _worker_loop(q: "queue.Queue"):
    while True:
        item = q.get()
        if item is None:
            return
        process_message(*item)


def start_mqtt():
    global _client, _connected, _last_error, _queue, _worker
    if not settings.mqtt_enabled:
        log.info("MQTT disabled; running API-only mode")
        return None
    if _is_public_broker(settings.mqtt_host) and not settings.mqtt_dev_public_broker:
        _last_error = "Refusing to connect to a public broker. Use a private broker or set MQTT_DEV_PUBLIC_BROKER=true (development only)."
        log.error(_last_error)
        return None
    if _is_public_broker(settings.mqtt_host):
        log.warning("DEVELOPMENT ONLY: using a public MQTT broker. Anyone can read telemetry and publish pump commands.")
    try:
        import paho.mqtt.client as mqtt

        _queue = queue.Queue(maxsize=max(10, settings.mqtt_queue_size))
        _worker = threading.Thread(target=_worker_loop, args=(_queue,), name="mqtt-worker", daemon=True)
        _worker.start()
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="greetopia-backend")
        if settings.mqtt_username:
            client.username_pw_set(settings.mqtt_username, settings.mqtt_password or None)
        if settings.mqtt_tls:
            client.tls_set(ca_certs=settings.mqtt_ca_file or None, cert_reqs=ssl.CERT_REQUIRED)

        def on_connect(client, userdata, flags, reason_code, properties):
            global _connected, _last_connected_at, _last_error
            if reason_code == 0:
                _connected = True
                _last_connected_at = datetime.now(timezone.utc).isoformat()
                _last_error = None
                for topic in SUBSCRIPTIONS:  # explicit subscriptions: "plants/+/+" would miss nested soil topics
                    client.subscribe(topic, qos=1)
                log.info("MQTT connected and subscribed")
            else:
                _connected = False
                _last_error = f"Connection rejected: {reason_code}"
                log.error("MQTT connection rejected: %s", reason_code)

        def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
            global _connected, _last_error
            _connected = False
            if reason_code:
                _last_error = f"Disconnected: {reason_code}"
                log.warning("MQTT disconnected: %s; automatic reconnect with backoff", reason_code)

        def on_message(client, userdata, msg):
            _stats["received"] += 1
            try:
                _queue.put_nowait((msg.topic, bytes(msg.payload), bool(msg.retain)))
            except queue.Full:
                _stats["dropped_queue_full"] += 1

        client.on_connect, client.on_disconnect, client.on_message = on_connect, on_disconnect, on_message
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        client.connect_async(settings.mqtt_host, settings.mqtt_port, settings.mqtt_keepalive)
        client.loop_start()
        _client = client
        return client
    except Exception as exc:
        _connected = False
        _last_error = str(exc)[:300]
        log.exception("Could not start MQTT client")
        return None


def publish_water(plant_id: str, duration_seconds: int):
    """Publish exactly 'ON:<1..15>'. Returns published=True only after the broker acknowledged (QoS 1).

    NOTE: broker acceptance is NOT proof that the pump ran; see device_state for reconciliation."""
    topic = f"plants/{plant_id}/water"
    if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int) or not 1 <= duration_seconds <= FIRMWARE_MAX_PUMP_S:
        return {"published": False, "topic": topic, "payload": None, "message": f"Duration must be an integer 1..{FIRMWARE_MAX_PUMP_S} seconds."}
    payload = f"ON:{duration_seconds}"
    if _client is None or not settings.mqtt_enabled or not _client.is_connected():
        return {"published": False, "topic": topic, "payload": payload, "message": "MQTT is disabled or disconnected; command was not sent."}
    info = _client.publish(topic, payload=payload, qos=1, retain=False)
    if info.rc != 0:
        return {"published": False, "topic": topic, "payload": payload, "message": f"MQTT publish failed with code {info.rc}"}
    try:
        info.wait_for_publish(timeout=3)
    except Exception:
        pass
    if not info.is_published():
        return {"published": False, "topic": topic, "payload": payload, "message": "Broker did not acknowledge the command in time; treat the outcome as unconfirmed."}
    return {"published": True, "topic": topic, "payload": payload, "message": "Command accepted by the MQTT broker (not yet confirmed by the device)."}


def stop_mqtt():
    global _client, _connected, _queue, _worker
    if _client:
        try:
            _client.disconnect()
            _client.loop_stop()
        finally:
            _client = None
            _connected = False
    if _queue is not None and _worker is not None:
        try:
            _queue.put_nowait(None)
        except queue.Full:
            pass
        _worker.join(timeout=3)
    _queue, _worker = None, None

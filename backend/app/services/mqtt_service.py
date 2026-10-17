import logging, ssl
from app.core.config import settings
from app.services.telemetry import ingest_mqtt
log=logging.getLogger(__name__)
_client=None
_connected=False
_last_connected_at=None
_last_error=None

def mqtt_status():
    """Return observable MQTT state without exposing broker credentials."""
    return {
        'enabled': bool(settings.mqtt_enabled),
        'connected': bool(_client and _client.is_connected() and _connected),
        'last_connected_at': _last_connected_at,
        'last_error': _last_error,
    }

def start_mqtt():
    global _client, _connected, _last_error
    if not settings.mqtt_enabled:
        log.info('MQTT disabled; running API-only mode')
        return None
    try:
        import paho.mqtt.client as mqtt
        client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='greetopia-backend')
        if settings.mqtt_username: client.username_pw_set(settings.mqtt_username, settings.mqtt_password or None)
        if settings.mqtt_tls: client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        def on_connect(client, userdata, flags, reason_code, properties):
            global _connected, _last_connected_at, _last_error
            if reason_code == 0:
                from datetime import datetime, timezone
                _connected = True
                _last_connected_at = datetime.now(timezone.utc).isoformat()
                _last_error = None
                # Exact subscriptions avoid relying on a wildcard that misses nested soil topics.
                client.subscribe('plants/+/soil/#', qos=1)
                client.subscribe('plants/+/temp', qos=1)
                client.subscribe('plants/+/humidity', qos=1)
                client.subscribe('plants/+/status', qos=1)
                client.subscribe('plants/+/leaf_wetness', qos=1)
                log.info('MQTT connected and subscribed')
            else:
                _connected = False
                _last_error = f'Connection rejected: {reason_code}'
                log.error('MQTT connection rejected: %s', reason_code)
        def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
            global _connected, _last_error
            _connected = False
            if reason_code:
                _last_error = f'Disconnected: {reason_code}'
                log.warning('MQTT disconnected: %s; client will attempt reconnection', reason_code)
            else:
                log.info('MQTT client disconnected')
        def on_message(client, userdata, msg):
            try: ingest_mqtt(msg.topic, msg.payload)
            except Exception: log.exception('Rejected MQTT message on %s', msg.topic)
        client.on_connect=on_connect; client.on_disconnect=on_disconnect; client.on_message=on_message
        client.reconnect_delay_set(min_delay=1,max_delay=30)
        client.connect_async(settings.mqtt_host, settings.mqtt_port, settings.mqtt_keepalive)
        client.loop_start(); _client=client
        return client
    except Exception as exc:
        _connected = False
        _last_error = str(exc)[:300]
        log.exception('Could not start MQTT client')
        return None

def publish_water(plant_id: str, duration_seconds: int):
    payload = f'ON:{duration_seconds}'  # Always explicit: firmware's plain ON means its full 15-second maximum.
    topic=f'plants/{plant_id}/water'
    if _client is None or not settings.mqtt_enabled or not _client.is_connected():
        return {'published':False,'topic':topic,'payload':payload,'message':'MQTT is disabled or disconnected; command was not sent.'}
    info=_client.publish(topic,payload=payload,qos=1,retain=False)
    return {'published':info.rc == 0,'topic':topic,'payload':payload,'message':'Command queued for MQTT broker.' if info.rc == 0 else f'MQTT publish failed with code {info.rc}'}

def stop_mqtt():
    global _client, _connected
    if _client:
        try:
            _client.disconnect()
            _client.loop_stop()
        finally:
            _client=None
            _connected=False

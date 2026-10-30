# Private MQTT broker

1. Create the password file (one user per node plus the backend):
   ```
   docker run --rm -it -v "$PWD/deploy/mosquitto:/mosquitto/config" eclipse-mosquitto:2 \
     sh -c "touch /mosquitto/config/passwd && mosquitto_passwd -b /mosquitto/config/passwd greetopia_backend '<password>' && mosquitto_passwd -b /mosquitto/config/passwd plant01 '<password>'"
   ```
2. Start: `docker compose --profile mqtt up -d`
3. Backend `.env`: `MQTT_ENABLED=true`, `MQTT_HOST=mosquitto`, `MQTT_USERNAME=greetopia_backend`, `MQTT_PASSWORD=...`
4. Node `secrets.h`: the node user/password above. For anything beyond a trusted LAN add a TLS listener and set `USE_TLS 1`.

The ACL means a compromised or malicious client cannot publish `plants/+/water`, which is what protects the pump.
Do not use `broker.hivemq.com` or other public brokers except for throw-away bench tests (`MQTT_DEV_PUBLIC_BROKER=true`).

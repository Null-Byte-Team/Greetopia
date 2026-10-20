"""Publish sample telemetry for UI testing. Requires `pip install paho-mqtt`.

Example: python simulator/mqtt_publisher.py --host 127.0.0.1 --plant plant01 --user plant01 --password ...
The simulator refuses well-known public brokers: never point test traffic at a shared broker that also controls real hardware.
"""
import argparse, random, time
import paho.mqtt.client as mqtt

PUBLIC = ("broker.hivemq.com", "test.mosquitto.org", "broker.emqx.io", "mqtt.eclipseprojects.io")
p = argparse.ArgumentParser()
p.add_argument('--host', default='127.0.0.1'); p.add_argument('--port', type=int, default=1883)
p.add_argument('--plant', default='plant01'); p.add_argument('--interval', type=float, default=10)
p.add_argument('--user', default=None); p.add_argument('--password', default=None)
p.add_argument('--tls', action='store_true'); p.add_argument('--allow-public-broker', action='store_true')
args = p.parse_args()
if args.host in PUBLIC and not args.allow_public_broker:
    raise SystemExit('Refusing to use a public broker. Use a private broker or pass --allow-public-broker for a throw-away bench test.')
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='irrigation-simulator')
if args.user: client.username_pw_set(args.user, args.password)
if args.tls: client.tls_set()
client.connect(args.host, args.port, 45); client.loop_start()
root = 42.0
try:
    while True:
        root = max(5, min(80, root + random.uniform(-1.5, 0.6)))
        values = {'soil/surface': max(0, min(100, root + random.uniform(-10, 10))), 'soil/mid': max(0, min(100, root + random.uniform(-5, 5))),
                  'soil/root': root, 'temp': 24 + random.uniform(-1, 1), 'humidity': 55 + random.uniform(-3, 3)}
        for metric, value in values.items():
            # same text formats as the firmware: integer soil %, 2-decimal temp/humidity
            text = str(int(round(value))) if metric.startswith('soil') else f'{value:.2f}'
            client.publish(f'plants/{args.plant}/{metric}', text, qos=1)
        print(f'published SIMULATED telemetry for {args.plant}: root={root:.1f}%')
        time.sleep(args.interval)
except KeyboardInterrupt:
    pass
finally:
    client.loop_stop(); client.disconnect()

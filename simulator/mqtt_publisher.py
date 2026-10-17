"""Publish sample telemetry for UI testing. Requires `pip install paho-mqtt`.

Example: python simulator/mqtt_publisher.py --host 127.0.0.1 --plant plant01
Use only with a test broker, never a shared public broker controlling real hardware.
"""
import argparse, random, time
import paho.mqtt.client as mqtt

p=argparse.ArgumentParser(); p.add_argument('--host',default='127.0.0.1'); p.add_argument('--port',type=int,default=1883); p.add_argument('--plant',default='plant01'); p.add_argument('--interval',type=float,default=10); args=p.parse_args()
client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='irrigation-simulator')
client.connect(args.host,args.port,45); client.loop_start()
root=42.0
try:
    while True:
        root=max(5,min(80,root+random.uniform(-1.5,0.6)))
        values={'soil/surface':max(0,min(100,root+random.uniform(-10,10))),'soil/mid':max(0,min(100,root+random.uniform(-5,5))),'soil/root':root,'temp':24+random.uniform(-1,1),'humidity':55+random.uniform(-3,3),'status':'idle'}
        for metric,value in values.items():
            client.publish(f'plants/{args.plant}/{metric}',str(round(value,1) if isinstance(value,float) else value),qos=1)
        print(f'published test telemetry for {args.plant}: root={root:.1f}%')
        time.sleep(args.interval)
except KeyboardInterrupt:
    pass
finally:
    client.loop_stop(); client.disconnect()

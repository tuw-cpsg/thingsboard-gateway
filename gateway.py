#!/usr/bin/python3

import yaml
import json

import time
import socket
import sys
import os
import random
import struct
from threading import Thread
from threading import Event
from gattlib import GATTRequester
from gattlib import DiscoveryService
from gattlib import EddystoneService
import paho.mqtt.client as mqtt

from eddystone_device import EddystoneDevice
import ibeacon_device

VERSION = '0.1.0-3'

config = None
for loc in os.curdir, os.path.expanduser('~'), '/etc/thingsboard':
    try:
        with open(os.path.join(loc,'config.yaml'), 'r') as stream:
            try:
                config = yaml.load(stream, Loader=yaml.FullLoader)
                break
            except yaml.YAMLError as exc:
                print(exc)
                quit()
    except IOError as exc:
        print(exc)

if config == None:
    print('No valid configuration found.')
    quit()

BEACON_UUID = config['beacon']['uuid']
BEACON_TIMEOUT = config['beacon']['timeout']
THINGSBOARD_HOST = config['thingsboard']['host']
THINGSBOARD_PORT = config['thingsboard']['port']
ACCESS_TOKEN = config['thingsboard']['access_token']
SENSOR_HANDLES = config['sensor']['handles']

def on_connect(mqttc, obj, flags, rc):
    print('rc: ' + str(rc))

def on_message(mqttc, obj, msg):
    print(msg.topic + ' ' + str(msg.qos) + ' ' + str(msg.payload))
    # Decode JSON request
    data = json.loads(msg.payload)
    # Check request method
    if data['method'] == 'checkStatus':
        # Reply with GPIO status
        mqttc.publish(msg.topic.replace('request', 'response'), json.dumps(tmp), 1)
    elif data['method'] == 'setValue':
        # Update GPIO status and reply
        tmp['value'] = data['params']
        mqttc.publish(msg.topic.replace('request', 'response'), json.dumps(tmp), 1)
        mqttc.publish('v1/devices/me/attributes', json.dumps(tmp), 1)
        if data['params'] == 'reboot':
            Thread(target = reboot).start()
        elif data['params'] == 'poweroff':
            Thread(target = poweroff).start()

def on_publish(mqttc, obj, mid):
    print('mid: ' + str(mid))

def on_subscribe(mqttc, obj, mid, granted_qos):
    print('Subscribed: ' + str(mid) + ' ' + str(granted_qos))

def on_log(mqttc, obj, level, string):
    print(string)

def ip_info_msg():
    s = 0;
    sensor_data = {'id': '127.0.0.1'} 
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        sensor_data['id'] = s.getsockname()[0]
    except:
        sensor_data['id'] = '127.0.0.1'
    finally:
        s.close()
    return sensor_data

tmp = {'method': 'checkStatus', 'value': True}

# Connect to ThingsBoard using default MQTT port and 60 seconds keepalive interval

# If you want to use a specific client id, use
# mqttc = mqtt.Client('client-id')
# but note that the client id must be unique on the broker. Leaving the client
# id parameter empty will generate a random id for you.
mqttc = mqtt.Client()
mqttc.username_pw_set(ACCESS_TOKEN)

mqttc.on_message = on_message
mqttc.on_connect = on_connect
mqttc.on_publish = on_publish
mqttc.on_subscribe = on_subscribe

# Uncomment to enable debug messages
mqttc.on_log = on_log
mqttc.connect(THINGSBOARD_HOST, THINGSBOARD_PORT, 60)
mqttc.loop_start()
time.sleep(1)

#service = BeaconService()
eddystone_service = EddystoneService()
discovery_service = DiscoveryService()

# Subscribing to receive RPC requests
mqttc.subscribe('v1/devices/me/rpc/request/+')
# Sending current status
tmp['value'] = True;
tmp['version'] = VERSION;
mqttc.publish('v1/devices/me/attributes', json.dumps(tmp), 1)
print(json.dumps(tmp))
# Sending id data to ThingsBoard
mqttc.publish('v1/devices/me/telemetry', json.dumps(ip_info_msg()), 1)
print(json.dumps(ip_info_msg()))

readers = {}

try:
    while True:
        devices = eddystone_service.scan(2)
        for address, data in list(devices.items()):
            b = EddystoneDevice(mqttc, data, address, BEACON_TIMEOUT)
            if b._url == 'http://www.afarcloud.eu/':
                print("AFC Eddystone URL found: {} ({})".format(b._address, b._url))
                if address not in readers:
                    readers[address] = b
                if readers[address].state_connect == True:
                    continue
                if (time.time() - readers[address].last_synced) > 900:
                    readers[address].start(True)
                    time.sleep(2)
        time.sleep(10)

except KeyboardInterrupt:
    pass

except Exception as e:
    print(str(e))

#loop_stop(force=False)
for address, reader in readers.items():
    reader.set_disconnect()

mqttc.disconnect()
print('Done.')

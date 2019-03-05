#!/usr/bin/python

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
from bluetooth.ble import BeaconService
import paho.mqtt.client as mqtt

VERSION = '0.1.0-2'

config = None
for loc in os.curdir, os.path.expanduser('~'), '/etc/thingsboard':
    try:
        with open(os.path.join(loc,'config.yaml'), 'r') as stream:
            try:
                config = yaml.load(stream)
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

class Device(GATTRequester):
    def __init__(self, mqttc, data, address, *args):
        #GATTRequester.__init__(self, *args)
        GATTRequester.__init__(self, address, False)

        self.received = Event()

        self._mqttc = mqttc

        self._uuid = data[0]
        self._major = data[1]/256
        self._minor = data[2]/256
        self._power = data[3]
        self._rssi = data[4]

        self._address = address

        self.state_connect = True

        self.handle_to_name = {}

    def on_notification(self, handle, data):
        # print("{:x} = {:x}".format(handle, data))
        # print("{:x} = {:x}".format(handle, struct.unpack_from('<h', data, 3)[0]))
        if self._major == 101:
            self.unpack_and_send_telemetry_msg(data)
        else:
            self.send_telemetry_msg(handle, data)
        self.received.set()

    def conn(self):
        print('Connecting to {}'.format(self._address))
        sys.stdout.flush()
        self.connect(True, 'random')
        self.send_connect_msg()
        self.send_attributes_msg()

    def disc(self):
        print('Disconnecting from {}'.format(self._address))
        self.send_disconnect_msg()
        self.disconnect()

    def connect_to_handle(self, handle):
        attempt = 0
        while attempt < 3:
            try:
                self.write_by_handle(handle, str('\1\0'))
                break
            except Exception as e:
                print('Error setting handle {:x} for {}'.format(handle, self._address))
                attempt += 1
                time.sleep(random.randint(1, 5))
        if attempt > 2:
            print('Error setting handle {:x} 3 times for {}, aborting'.format(handle, self._address))
            self.state_connect = False

    def send_data(self):
        characteristics = self.discover_characteristics()
        for characteristic in characteristics:
            if characteristic['uuid'] not in SENSOR_HANDLES.keys():
                continue
            Thread(target = self.connect_to_handle,
                    kwargs={'handle': characteristic['value_handle']+1}).start()
            self.handle_to_name[characteristic['value_handle']] = SENSOR_HANDLES[characteristic['uuid']]

    def set_disconnect(self):
        self.state_connect = False

    def start(self):
        self.state_connect = True
        Thread(target = self.wait_notification).start()

    def wait_notification(self):
        self.conn()
        self.send_data()
        while self.state_connect:
            self.received.clear()
            if not self.received.wait(BEACON_TIMEOUT):
                print 'Timeout reading from {}'.format(self._address)
                self.state_connect = False
                break
            #self.send_telemetry_msg(self.requester.get_data())
        self.disc()

    def __str__(self):
        ret = 'Beacon: address:{ADDR} uuid:{UUID} major:{MAJOR}'\
                ' minor:{MINOR} txpower:{POWER} rssi:{RSSI}'\
                .format(ADDR=self._address, UUID=self._uuid, MAJOR=self._major,
                        MINOR=self._minor, POWER=self._power, RSSI=self._rssi)
        return ret

    def connect_msg(self):
        ret = {'device': self._address}
        return ret

    def attributes_msg(self):
        ret = { self._address:
                {
                    'major': self._major,
                    'minor': self._minor,
                    'txpower': self._power,
                    'rssi': self._rssi
                    }
                }
        return ret

    def send_connect_msg(self):
        self._mqttc.publish('v1/gateway/connect', json.dumps(b.connect_msg()), 1)

    def send_attributes_msg(self):
        self._mqttc.publish('v1/gateway/attributes', json.dumps(b.attributes_msg()), 1)

    def send_disconnect_msg(self):
        self._mqttc.publish('v1/gateway/disconnect', json.dumps(b.connect_msg()), 1)

    def send_telemetry_msg(self, handle, data):
        ts = int(round(time.time() * 1000))
        jdata = {}

        if self.handle_to_name[handle] == 'battery':
            jdata['battery']        = (struct.unpack_from('<h', data, 3)[0])
        elif self.handle_to_name[handle] == 'temperature':
            temp = struct.unpack_from('<h', data, 3)[0]
            if(tmp > -1000):
                jdata['temperature']    = temp / 16.0
        elif self.handle_to_name[handle] == 'moisture':
            jdata['moisture']       = (struct.unpack_from('<h', data, 3)[0])

        jdata = { self._address: [ {'ts': ts, 'values': jdata } ] }
        #print(json.dumps(jdata))
        self._mqttc.publish('v1/gateway/telemetry', json.dumps(jdata), 1)

    def unpack_and_send_telemetry_msg(self, data):
        ts = int(round(time.time() * 1000))
        jdata = {}

        if self._major == 101:
            jdata['timestamp']      = (struct.unpack_from('<I', data, 3 +  0)[0])
            jdata['temperature']    = (struct.unpack_from('<H', data, 3 +  4)[0] / 512.0 - 25.0)
            jdata['humidity']       = (struct.unpack_from('<H', data, 3 +  6)[0] / 512.0)
            jdata['pressure']       = (struct.unpack_from('<f', data, 3 +  8)[0])
            jdata['battery']        = (struct.unpack_from('<B', data, 3 + 19)[0])
            tmp = (struct.unpack_from('<H', data, 3 + 12))[0]
            if tmp < 32768:
                jdata['eco2']       = tmp
            tmp = (struct.unpack_from('<H', data, 3 + 14))[0]
            if tmp < 32768:
                jdata['tvoc']       = tmp
            tmp = (struct.unpack_from('<B', data, 3 + 16))[0]
            if tmp > 0:
                jdata['precipitation'] = tmp * 0.1

            jdata = { self._address: [ {'ts': ts, 'values': jdata } ] }
            #print(json.dumps(jdata))
            self._mqttc.publish('v1/gateway/telemetry', json.dumps(jdata), 1)

def poweroff():
    time.sleep(1)
    os.system('/bin/systemctl poweroff')

def reboot():
    time.sleep(1)
    os.system('/bin/systemctl reboot')

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

service = BeaconService()

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
        devices = service.scan(2)
        for address, data in list(devices.items()):
            b = Device(mqttc, data, address)
            if b._uuid == BEACON_UUID:
                if address not in readers:
                    readers[address] = b
                readers[address].start()
        time.sleep(10)

except KeyboardInterrupt:
    pass

except Exception as e:
    print str(e)

#loop_stop(force=False)
for address, reader in readers.items():
    reader.set_disconnect()

mqttc.disconnect()
print('Done.')

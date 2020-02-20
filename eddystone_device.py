import logging

import sys
import json
import paho.mqtt.client as mqtt
import struct
import time

from datetime import datetime
from gattlib import GATTRequester
from threading import Event
from threading import Thread

AFC_GSS_UUID                = '8fee1801-3c17-4189-8556-a293fa6b2739'
AFC_TIMESTAMP_UUID          = '8fee2901-3c17-4189-8556-a293fa6b2739'
AFC_SOIL_TEMPERATURE_UUID   = '8fee2917-3c17-4189-8556-a293fa6b2739'
AFC_SOIL_HUMIDITY_UUID      = '8fee2918-3c17-4189-8556-a293fa6b2739'
AFC_BATTERY_VOLTAGE_UUID    = '8fee2919-3c17-4189-8556-a293fa6b2739'

GEN_CTS_UUID                = '00001805-0000-1000-8000-00805f9b34fb'
GEN_CTS_CT_UUID             = '00002a2b-0000-1000-8000-00805f9b34fb'

class EddystoneDevice(GATTRequester):
    def __init__(self, mqttc, data, address, timeout, *args):
        #GATTRequester.__init__(self, *args)
        GATTRequester.__init__(self, address, False)

        self.received = Event()

        self._mqttc = mqttc
        self._address = address
        self._timeout = timeout
        self._frame_type    = data[1]
        self._power         = data[2]
        self._data          = data[3:]
        self._uri           = 0
        self._url           = ''
        
        self.value_handle = 0;
        self.cccd_handle  = 0;
        
        self.last_synced  = 0;
        
        self.jdata = {self._address: [] }

        if self._frame_type == 16:
            url = bytes(self._data)
            if url[0] == 0:
                url = b'http://www.' + url[1:]
            elif url[0] == 1:
                url = b'https://www.' + url[1:]
            elif url[0] == 2:
                url = b'http://' + url[1:]
            elif url[0] == 3:
                url = b'https://' + url[1:]
                
            url = url.replace(b'\x03', b'.net/')
            self._url = url.decode()

        self.state_connect = False

        self.handle_to_name = {}

    def on_indication(self, handle, data):
        datasets = struct.unpack_from('<B', data, 3)[0]
        if datasets == 0:
            self.received.set()
            self.state_connect = False
            return
        
        offset = 4
        for i in range(0, 1):
            offset = self.send_telemetry_msg(data, offset)
        
        self.received.set()

    def conn(self):
        logging.info('Connecting to {}'.format(self._address))
        sys.stdout.flush()
        self.connect(True, 'random')
        #self.send_connect_msg()
        self.send_attributes_msg()
        primaries = self.discover_primary()
        for primary in primaries:
            if primary['uuid'] == AFC_GSS_UUID:
                self.value_handle = primary['start'] + 2;
                self.cccd_handle  = primary['start'] + 3;
                
                logging.info("AFC primary service:  {}".format(primary))
                self.descriptors = self.discover_descriptors(self.cccd_handle + 1, primary['end'], '')
                for desc in self.descriptors:
                    logging.info("AFC descriptor found: {}".format(desc))
            elif primary['uuid'] == GEN_CTS_UUID:
                cts_descriptors = self.discover_descriptors(primary['start'], primary['end'], GEN_CTS_CT_UUID)
                self.cts_ct_handle = 0
                for desc in cts_descriptors:
                    if desc['uuid'] == GEN_CTS_CT_UUID:
                        self.cts_ct_handle = desc['handle']

    def disc(self):
        logging.info('Disconnecting from {}'.format(self._address))
        #self.send_disconnect_msg()
        self.disconnect()

    def connect_to_handle(self, handle):
        attempt = 0
        while attempt < 3:
            try:
                self.write_by_handle(handle, b'\x02')
                break
            except Exception as e:
                logging.error('Error setting handle {:x} for {}'.format(handle, self._address))
                attempt += 1
                time.sleep(random.randint(1, 5))
        if attempt > 2:
            logging.debug('Error setting handle {:x} 3 times for {}, aborting'.format(handle, self._address))
            self.state_connect = False

    def enable_indications(self):
        if self.cccd_handle != 0:
            Thread(target = self.connect_to_handle,
                kwargs={'handle': self.cccd_handle}).start()

    def set_disconnect(self):
        self.state_connect = False

    def start(self, threaded = False):
        self.state_connect = True
        if threaded == True:
            Thread(target = self.start_synchronization).start()
        else:
            self.start_synchronization()

    def start_synchronization(self):
        self.conn()
        self.enable_indications()
        while self.state_connect:
            self.received.clear()
            if not self.received.wait(self._timeout):
                logging.debug('Timeout reading from {}'.format(self._address))
                self.state_connect = False
                break
            #self.send_telemetry_msg(self.requester.get_data())
        self.sync_time()
        self.last_synced = time.time();
        self.disc()
        
        print(json.dumps(self.jdata))

    def sync_time(self):
        if self.cts_ct_handle == 0:
            return 
        utctime = datetime.utcnow()
        bt_date_time = struct.pack('<HBBBBBBBB',
                                   utctime.year, utctime.month, utctime.day,
                                   utctime.hour, utctime.minute, utctime.second,
                                   0, int(utctime.microsecond/3906.25), 0)
        self.write_by_handle(self.cts_ct_handle, bt_date_time)

    def __str__(self):
        ret = 'EddystoneBeacon: address:{ADDR}'\
                .format(ADDR=self._address)
        return ret

    def connect_msg(self):
        ret = {'device': self._address}
        return ret

    def attributes_msg(self):
        ret = { self._address:
                {
                    'txpower': self._power
                    #'rssi': self._rssi
                    }
                }
        return ret

    def send_connect_msg(self):
        self._mqttc.publish('v1/gateway/connect', json.dumps(self.connect_msg()), 1)

    def send_attributes_msg(self):
        self._mqttc.publish('v1/gateway/attributes', json.dumps(self.attributes_msg()), 1)

    def send_disconnect_msg(self):
        self._mqttc.publish('v1/gateway/disconnect', json.dumps(self.connect_msg()), 1)

    def send_telemetry_msg(self, data, _offset):
        ts = int(round(time.time() * 1000))
        jdata = {}

        offset = _offset
        for desc in self.descriptors:
            if desc['uuid'] == AFC_TIMESTAMP_UUID:
                ts = (struct.unpack_from('<I', data, offset)[0] * 1000)
                offset = offset + 4;
            
            elif desc['uuid'] == AFC_BATTERY_VOLTAGE_UUID:
                jdata['battery'] = (struct.unpack_from('<H', data, offset)[0] / 100.0)
                offset = offset + 2;
            
            elif desc['uuid'] == AFC_SOIL_TEMPERATURE_UUID:
                jdata['temperature'] = (struct.unpack_from('<h', data, offset)[0] / 100.0)
                offset = offset + 2;

            elif desc['uuid'] == AFC_SOIL_HUMIDITY_UUID:
                jdata['moisture'] = (struct.unpack_from('<H', data, offset)[0] / 100.0)
                offset = offset + 2;

        self.jdata[self._address].append({'ts': ts, 'values': jdata})
        jdata = { self._address: [ {'ts': ts, 'values': jdata } ] }
        
        #print(json.dumps(jdata))
        self._mqttc.publish('v1/gateway/telemetry', json.dumps(jdata), 1)
        
        return offset

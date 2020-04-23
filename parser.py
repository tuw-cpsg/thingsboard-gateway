import sys
import dbus
import time

import logging
import json

from threading import Condition, Lock
from datetime import datetime

import dbluez
import struct

AFC_GSS_UUID                = '8fee1801-3c17-4189-8556-a293fa6b2739'
AFC_GSC_UUID                = '8fee2a01-3c17-4189-8556-a293fa6b2739'
AFC_TIMESTAMP_UUID          = '8fee2901-3c17-4189-8556-a293fa6b2739'
AFC_AMB_TEMPERATURE_UUID    = '8fee2902-3c17-4189-8556-a293fa6b2739'
AFC_AMB_HUMDITY_UUID        = '8fee2903-3c17-4189-8556-a293fa6b2739'
AFC_ATM_PRESSURE_UUID       = '8fee2916-3c17-4189-8556-a293fa6b2739'
AFC_SOIL_TEMPERATURE_UUID   = '8fee2917-3c17-4189-8556-a293fa6b2739'
AFC_SOIL_HUMIDITY_UUID      = '8fee2918-3c17-4189-8556-a293fa6b2739'
AFC_BATTERY_VOLTAGE_UUID    = '8fee2919-3c17-4189-8556-a293fa6b2739'

AFC_SOIL_HUMIDITY_L_UUID    = '8fee29a1-3c17-4189-8556-a293fa6b2739'
AFC_SOIL_HUMIDITY_H_UUID    = '8fee29a2-3c17-4189-8556-a293fa6b2739'

GEN_CTS_UUID                = '00001805-0000-1000-8000-00805f9b34fb'
GEN_CTS_CT_UUID             = '00002a2b-0000-1000-8000-00805f9b34fb'

AFC_SYNC_DATA = {
    AFC_TIMESTAMP_UUID: {
        'name': 'timestamp',
        'size': 4,
        'type': '<I',
        'multiplicator': 1000
    },
    AFC_BATTERY_VOLTAGE_UUID: {
        'name': 'battery',
        'size': 2,
        'type': '<H',
        'multiplicator': 0.01
    },
    AFC_SOIL_TEMPERATURE_UUID: {
        'name': 'temperature',
        'size': 2,
        'type': '<h',
        'multiplicator': 0.01
    },
    AFC_SOIL_HUMIDITY_UUID: {
        'name': 'moisture',
        'size': 2,
        'type': '<H',
        'multiplicator': 0.01
    },
    AFC_AMB_TEMPERATURE_UUID: {
        'name': 'temperature',
        'size': 2,
        'type': '<h',
        'multiplicator': 0.01
    },
    AFC_AMB_HUMDITY_UUID: {
        'name': 'humidity',
        'size': 2,
        'type': '<H',
        'multiplicator': 0.01
    },
    AFC_ATM_PRESSURE_UUID: {
        'name': 'pressure',
        'size': 4,
        'type': '<I',
        'multiplicator': 0.001
    },
    AFC_SOIL_HUMIDITY_L_UUID: {
        'name': 'moisture_low',
        'size': 2,
        'type': '<H',
        'multiplicator': 1
    },
    AFC_SOIL_HUMIDITY_H_UUID: {
        'name': 'moisture_high',
        'size': 2,
        'type': '<H',
        'multiplicator': 1
    },
}

class Thingsboard:
    
    mutex = Lock()
    
    def __init__(self, device):
        self._device = device
        self._cv  = Condition()
        
        self._ccv = False
        
        self.jdata = {self._device._address: [] }
        
    def __enter__(self):
        None
    
    def __exit__(self):
        None
        
    def startSynchronization(self, lock = None):
        self._lock = lock
        logging.info('Connecting to remote device')
        self._device.connect(self.discoveryComplete)
        logging.info('Waiting for service discovery to be completed')

    def synchronizeTime(self):
        utctime = datetime.utcnow()
        bt_date_time = struct.pack('<HBBBBBBBB',
                                   utctime.year, utctime.month, utctime.day,
                                   utctime.hour, utctime.minute, utctime.second,
                                   0, int(utctime.microsecond/3906.25), 0)
        logging.info('Writing time info to remote CTS')
        self._cts.WriteValue(bt_date_time, {})

    def removeDevice(self):
        self._device.remove()
    
    def discoveryComplete(self):        
        logging.info('Discovery completed')
        self._ccv = True
        self._afc_descriptors = {}
        self._sc_cccd = None
        self._cts = None

        if GEN_CTS_CT_UUID in self._device.characteristics: 
            logging.info('Found CTS')
            self._cts = self._device.characteristics[GEN_CTS_CT_UUID]
        
        if AFC_GSC_UUID in self._device.characteristics:
            characteristic = self._device.characteristics[AFC_GSC_UUID]
            for key in sorted(self._device.descriptors.keys()):
                if key.startswith(characteristic.object_path):
                    uuid = dbluez.GetDescriptorProperty(self._device.descriptors[key], 'UUID')
                    if uuid == dbluez.BLE_GATT_CCCD:
                        self._sc_cccd = self._device.descriptors[key]
                    else:
                        self._afc_descriptors[key] = uuid
                        
            if self._sc_cccd != None:
                self._char_sig_rcv = dbluez.GetPropertiesChangedCb(characteristic, self.indication_cb)
                logging.info('Start notifications/indications')
                #flags = dbluez.GetDescriptorProperty(self._sc_cccd, 'Flags')
                #logging.info('Flags of CCCD: {}'.format(flags))
                #self._sc_cccd.ReadValue({})
                characteristic.StartNotify()
                #self._sc_cccd.WriteValue(bytes([0x02]), {})
            
        else:
            logging.info('Disconnecting from remote device')
            self._device.disconnect()
    
    def indication_cb(self, properties, changed_props, invalidated_props):
        if 'Value' not in changed_props:
            return
        
        data = bytes(changed_props['Value'])
        logging.info('Received {} bytes of data: {}'.format(len(data), data))
        
        if data == b'\x00':
            logging.info('Finished data receiption.')
            self.synchronizeTime()
            self._char_sig_rcv.remove()
            logging.info('Disconnecting from remote device')
            self._device.disconnect()
            if len(self.jdata[self._device._address]) > 0:
                print('{}'.format(json.dumps(self.jdata)), flush=True)
            self._lock.release()
            self._lock = None
            return
        
        ts = int(round(time.time() * 1000))
        jdata = {}
        
        offset = 1
        dataset_cnt = data[0]
        for x in range(0, dataset_cnt):
            for desc in self._afc_descriptors.values():
                if desc == dbluez.BLE_GATT_CCCD:
                    continue
                
                if desc == AFC_TIMESTAMP_UUID:
                    ts = (struct.unpack_from('<I', data, offset)[0] * 1000)
                    offset = offset + 4;
                    continue
                
                if desc == AFC_SOIL_HUMIDITY_L_UUID:
                    self._calibration = True
                    
                jdata[AFC_SYNC_DATA[desc]['name']] = \
                    (struct.unpack_from(AFC_SYNC_DATA[desc]['type'], data, offset)[0]) \
                    * AFC_SYNC_DATA[desc]['multiplicator'] 
                offset = offset + AFC_SYNC_DATA[desc]['size']

            self.jdata[self._device._address].append({'ts': ts, 'values': jdata})

            logging.info('Data count in JSON: {}'.format(len(self.jdata[self._device._address])))
            if len(self.jdata[self._device._address]) > 4:
                print('{}'.format(json.dumps(self.jdata)), flush=True)
                self.jdata = {self._device._address: [] }
            

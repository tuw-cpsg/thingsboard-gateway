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

AFC_ACTUATOR_OUT_UUID       = '8fee29a3-3c17-4189-8556-a293fa6b2739'

AFC_ANS_UUID                = '8fee1805-3c17-4189-8556-a293fa6b2739'
AFC_ANS_NNC_UUID            = '8fee2a31-3c17-4189-8556-a293fa6b2739'

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
    AFC_ACTUATOR_OUT_UUID: {
        'name': 'actuator_out',
        'size': 1,
        'type': '<B',
        'multiplicator': 1
    }
}

class Thingsboard:
    
    mutex = Lock()
    
    def __init__(self, device):
        self._logger = logging.getLogger('{}[{}]'.format(__name__, device.getAddress()))
        self._device = device
        self._cv  = Condition()
        
        self._ccv = False
        
        self._node_name = None
        self._jdata = []
        
    def __enter__(self):
        None
    
    def __exit__(self):
        None
        
    def startSynchronization(self, lock = None):
        self._logger.info('Start synchronization')
        self._lock = lock
        self._device.connect(self.disconnect_cb, self.discoveryComplete)
        self._sync_cnt = 0
        self._byte_cnt = 0
        self._ind_cnt  = 0

    def endSynchronization(self):
        dis_time = time.time()
        self._logger.debug('End synchronization')
        self.synchronizeTime()
        cts_time = time.time()
        self._char_sig_rcv.remove()


        self._device.disconnect()

        if len(self._jdata) > 0:
            print('{}'.format(json.dumps({self._node_name: self._jdata})), flush=True)

        self._logger.info('Received {} data sets ({} bytes) with {} indications in {} s ({} {})'.format(self._sync_cnt, self._byte_cnt, self._ind_cnt, dis_time - self._indication_started, cts_time - dis_time, time.time() - dis_time))
        
        self._lock.release()
        self._lock = None

    def synchronizeTime(self):
        utctime = datetime.utcnow()
        bt_date_time = struct.pack('<HBBBBBBBB',
                                   utctime.year, utctime.month, utctime.day,
                                   utctime.hour, utctime.minute, utctime.second,
                                   0, int(utctime.microsecond/3906.25), 0)
        self._logger.debug('Writing time info to remote CTS')
        self._cts.WriteValue(bt_date_time, {})

    def getNodeName(self):
        if self._nnc == None:
            return self._device._address

        self._logger.info('Getting remote device name')
        return bytes(self._nnc.ReadValue({})).decode("utf-8")
        

    def removeDevice(self):
        self._device.remove()
    
    def disconnect_cb(self, is_connected):
        self._logger.info('Disconnect callback: {}'.format(is_connected))

        if is_connected == False:
            try:
                self._device.disconnect()
            except Exception as e:
                self._logger.error('Error disconnecting from device: {}'.format(e))

            if self._lock != None:
                self._lock.release()
                self._lock = None

    def discoveryComplete(self):        
        self._logger.info('Discovery completed')
        self._ccv = True
        self._afc_descriptors = {}
        self._sc_cccd = None
        self._nnc = None
        self._cts = None

        if AFC_ANS_NNC_UUID in self._device.characteristics:
            self._logger.info('Found AFC node name characteristics')
            self._nnc = self._device.characteristics[AFC_ANS_NNC_UUID]

        self._node_name = self.getNodeName()

        if GEN_CTS_CT_UUID in self._device.characteristics: 
            self._logger.info('Found CTS')
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
                self._logger.info('Start notifications/indications')
                self._indication_started = time.time()
                characteristic.StartNotify()
            
        else:
            self._logger.warning('No service found to synchronize, disconnecting')
            self._device.disconnect()
            self._logger.debug('Release lock')
            if self._lock != None:
                self._lock.release()
                self._lock = None
    
    def indication_cb(self, properties, changed_props, invalidated_props):
        if 'Value' in changed_props:
            data = bytes(changed_props['Value'])
            self._logger.debug('Received {} bytes of data'.format(len(data), data))
            
            if data == b'\x00':
                self.endSynchronization()
                return
            
            self._ind_cnt = self._ind_cnt + 1
            ts = int(round(time.time() * 1000))
            
            offset = 1
            dataset_cnt = data[0]
            self._sync_cnt = self._sync_cnt + dataset_cnt
            self._byte_cnt = self._byte_cnt + len(data)
            for x in range(0, dataset_cnt):
                jdata = {}
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

                self._jdata.append({'ts': ts, 'values': jdata})

                self._logger.debug('Data count in JSON: {}'.format(len(self._jdata)))
                if len(self._jdata) > 4:
                    print('{}'.format(json.dumps({self._node_name: self._jdata})), flush=True)
                    self._jdata = []
                
        if 'Notifying' in changed_props:
            self._logger.debug('Received notifying')

        if 'Value' not in changed_props and 'Notifying' not in changed_props:
            self._logger.warning('Unknown changed properties: {}'.format(changed_props))

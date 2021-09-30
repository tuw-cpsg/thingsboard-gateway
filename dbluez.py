#!/usr/bin/env python3

# inspired by: https://github.com/aykevl/pynus
# inspired by: https://github.com/michael-platzer/ble-data-hub

import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import logging

import time

DBUS_OBJ_MAN   = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROPS     = 'org.freedesktop.DBus.Properties'

BLUEZ          = 'org.bluez'
BLUEZ_ADAPTER  = 'org.bluez.Adapter1'
BLUEZ_DEVICE   = 'org.bluez.Device1'
BLUEZ_GATTSERV = 'org.bluez.GattService1'
BLUEZ_GATTCHAR = 'org.bluez.GattCharacteristic1'
BLUEZ_GATTDESC = 'org.bluez.GattDescriptor1'

EDDYSTONE_UUID = '0000feaa-0000-1000-8000-00805f9b34fb'

BLE_GATT_CCCD  = '00002902-0000-1000-8000-00805f9b34fb'

def GetServiceProperty(device, property):
    properties = dbus.Interface(device, DBUS_PROPS)
    return properties.Get(BLUEZ_GATTSERV, property)

def GetCharacteristicProperty(device, property):
    properties = dbus.Interface(device, DBUS_PROPS)
    return properties.Get(BLUEZ_GATTCHAR, property)

def GetDescriptorProperty(device, property):
    properties = dbus.Interface(device, DBUS_PROPS)
    return properties.Get(BLUEZ_GATTDESC, property)

def GetPropertiesChangedCb(device, cb):
    char_props = dbus.Interface(device, DBUS_PROPS)
    return char_props.connect_to_signal('PropertiesChanged', lambda *args: cb(*args))

#yes, you should get properties changed signals eg with rssi for those devices

class Scanner:
    def __init__(self, adapter, new_device_cb):
        self._adapter = adapter
        self._path = '/org/bluez/{}'.format(adapter)
        self._logger = logging.getLogger(__name__)
        
        self._sysbus = dbus.SystemBus()
        self._bluez = dbus.Interface(self._sysbus.get_object(BLUEZ, '/'), DBUS_OBJ_MAN)

        self._adapterobj = dbus.Interface(self._sysbus.get_object(BLUEZ, self._path), BLUEZ_ADAPTER)
        
        self._sig_recv_new = self._sysbus.add_signal_receiver(lambda *args: self._on_new_device(*args), dbus_interface=DBUS_OBJ_MAN, signal_name='InterfacesAdded')
        self._sig_recv_rem = self._sysbus.add_signal_receiver(lambda *args: self._on_rem_device(*args), dbus_interface=DBUS_OBJ_MAN, signal_name='InterfacesRemoved')
        self._sig_prop_chg = self._sysbus.add_signal_receiver(lambda *args: self._on_prop_changed(*args), dbus_interface=DBUS_OBJ_MAN, signal_name = "PropertiesChanged",
                                                              arg0 = "org.bluez.Device1", path_keyword = "path")

        self._new_device_cb = new_device_cb
        self._rem_dev_cb = None

    def __enter__(self):
        for path, interfaces in self._bluez.GetManagedObjects().items():
            if BLUEZ_DEVICE in interfaces:
                self._on_new_device(path, interfaces)

    def __exit__(self, type, value, traceback):    
        self._sig_recv_new.remove()
        self._sig_recv_rem.remove()
    
    def _on_new_device(self, path, interfaces):
        #print(path);
        if BLUEZ_DEVICE in interfaces:
            props = interfaces[BLUEZ_DEVICE]
            if EDDYSTONE_UUID in props['UUIDs']:
                data      = bytes(props['ServiceData'][EDDYSTONE_UUID])
                frametype = data[0]
                power     = data[1]
                url       = data[2:]
                if url[0] == 0:
                    url = b'http://www.' + url[1:]
                elif url[0] == 1:
                    url = b'https://www.' + url[1:]
                elif url[0] == 2:
                    url = b'http://' + url[1:]
                elif url[0] == 3:
                    url = b'https://' + url[1:]
                    
                url = url.replace(b'\x03', b'.net/')
                url = url.decode()
                
                self._new_device_cb(self._adapter, props['Address'], frametype, power, url)
            
    def _on_rem_device(self, path, interfaces):
        if BLUEZ_DEVICE in interfaces:
            if self._rem_dev_cb != None:
                self._rem_dev_cb(path)
    
    def _on_prop_changed(self, properties, changed_props, invalidated_props):
        self._logger.info('Changed properties: {}'.format(changed_props))
    
    def startScan(self):
        self._adapterobj.SetDiscoveryFilter({
            'Transport': 'le',
            'UUIDs': [EDDYSTONE_UUID]
            })
        self._adapterobj.StartDiscovery()
        
    def stopScan(self):
        self._adapterobj.StopDiscovery()

class Device:
    def __init__(self, adapter, address, frametype, power, url):
        self._logger  = logging.getLogger('{}[{}]'.format(__name__, address))
        self._adapter = adapter
        self._address = address
        self._frametype = frametype
        self._power   = power
        self._url     = url
        self._sig_recv = None
        self._connect_time = 0
        
        self._path = '/org/bluez/{}/dev_{}'.format(adapter, address.replace(':', '_'))
        
        self._sysbus = dbus.SystemBus()
        self._bluez  = dbus.Interface(self._sysbus.get_object(BLUEZ, '/'), DBUS_OBJ_MAN)
        self._adapterobj = dbus.Interface(self._sysbus.get_object(BLUEZ, '/org/bluez/{}'.format(self._adapter)), BLUEZ_ADAPTER)

        self._device = dbus.Interface(self._sysbus.get_object(BLUEZ, self._path), BLUEZ_DEVICE)
        
    def __del__(self):
        self._logger.debug('device {} deleted'.format(self._path))
        #self._adapterobj.RemoveDevice(self._path)

    def _on_prop_changed(self, properties, changed_props, invalidated_props):
        self._logger.debug('Changed properties: {}'.format(changed_props))

        if 'Connected' in changed_props:
            is_connected = bool(changed_props['Connected'])
            self._logger.debug('Connect property changed: {}'.format(is_connected))
            if is_connected == False:
                self._disconnect_cb(bool(changed_props['Connected']))
                return

        if 'ServicesResolved' in changed_props:
            self._probe_services()

    def _probe_services(self):
        man_objs = self._bluez.GetManagedObjects()

        self.characteristics = {}
        self.descriptors = {}
        for path, interfaces in man_objs.items():
            if path.startswith(self._path) and BLUEZ_GATTSERV in interfaces:
                props = interfaces[BLUEZ_GATTSERV]
                for c_path, c_ifaces in man_objs.items():
                    if not c_path.startswith(path):
                        continue
                    if BLUEZ_GATTCHAR in c_ifaces:
                        c_props = c_ifaces[BLUEZ_GATTCHAR]
                        self.characteristics[c_props['UUID']] = dbus.Interface(self._sysbus.get_object(BLUEZ, c_path), BLUEZ_GATTCHAR)
                    elif BLUEZ_GATTDESC in c_ifaces:
                        c_props = c_ifaces[BLUEZ_GATTDESC]
                        self.descriptors[c_path] = dbus.Interface(self._sysbus.get_object(BLUEZ, c_path), BLUEZ_GATTDESC)              
        
        if self._discovery_cb != None:
            self._discovery_cb()

    def connect(self, disconnect_cb = None, services_discovered_cb = None):
        self._logger.debug('Connecting')
        self._discovery_cb = services_discovered_cb
        self._disconnect_cb = disconnect_cb
        for x in range(0, 3):
            try:
                self._device.Connect()
                device_props = dbus.Interface(self._device, DBUS_PROPS)
                self._sig_recv = device_props.connect_to_signal('PropertiesChanged', lambda *args: self._on_prop_changed(*args))
                self._connect_time = time.time()
                return
            except Exception as e:
                self._logger.error('Error while connecting: {}'.format(e))
                time.sleep(5)
        self._logger.error('Error connecting 3 consequitve times. Aborting..')
        self._disconnect_cb(False)

    def disconnect(self):
        self._logger.debug('Disconnecting')
        if self._sig_recv != None:
            self._sig_recv.remove()
        self._device.Disconnect()
        if self._connect_time > 0:
            self._logger.info('Disconnected. Connected time: {} s'.format(time.time() - self._connect_time))
        
    def remove(self):
        self._adapterobj.RemoveDevice(self._path)

    def getAddress(self):
        return self._address

#!/usr/bin/env python3

import logging

import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

import dbluez
import parser

import threading
from threading import Lock
import time

import getopt, sys

DBUS_OBJ_MAN = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROPS = 'org.freedesktop.DBus.Properties'

BLUEZ = 'org.bluez'
BLUEZ_ADAPTER = 'org.bluez.Adapter1'
BLUEZ_DEVICE = 'org.bluez.Device1'
BLUEZ_GATTSERV = 'org.bluez.GattService1'
BLUEZ_GATTCHAR = 'org.bluez.GattCharacteristic1'

loop      = None
timer     = None
scanner   = None
log_level = None

def usage():
    print('Usage:')
    print('  gateway.py [options]')
    print('Options:')
    print('  -h, --help                Show help')
    print('  -i, --adapter=hciX        Specify local adapter interface')

def parse_options():
    global adapter
    global daemon
    global log_level
    
    try:
        opts, args = getopt.getopt(sys.argv[1:], "dhi:", ["help", "adapter="])
    except getopt.GetoptError as err:
        # print help information and exit:
        print(err)  # will print something like "option -a not recognized"
        usage()
        sys.exit(2)
    adapter = 'hci0'
    log_level = logging.INFO
    for o, a in opts:
        if o in ('-h', '--help'):
            usage()
            sys.exit()
        elif o in ('-d', '--daemon'):
            daemon = True
        elif o in ('-i', '--adapter'):
            adapter = a
        elif o in ('-V', '--verbose'):
            log_level = logging.DEBUG
        else:
            assert False, "unhandled option"

def new_device_cb(adapter, address, frametype, power, url):
    global logger
    global addresses_to_process
    global devices
    logger.info('Found new device: {} with \'{}\''.format(address, url))
    if url == 'http://www.afarcloud.eu/':
        device = dbluez.Device(adapter, address, frametype, power, url)
        afcdev = parser.Thingsboard(device)
        if address not in addresses_to_process:
            addresses_to_process.append(address)
        if address not in devices.keys():
            devices[address] = afcdev

def quit():
    global logger
    global loop
    global scanner
    global timer
    global devices
    global addresses_to_process
    global lock

    def sync():

        if len(addresses_to_process) > 0:
            address = addresses_to_process.pop()
            lock.acquire()
            devices[address].startSynchronization(lock)

            thread = threading.Thread(target=sync)
            thread.daemon = True
            thread.start()

        elif len(devices) > 0:
            logger.info('Waiting for last device to finish')
            lock.acquire()
            logger.info('Finished')
            lock.release()

            loop.quit()

        elif len(devices) == 0:
            loop.quit()

    lock = Lock()
    logger.info('Scan timeout')

    GLib.source_remove(timer)

    thread = threading.Thread(target=sync)
    thread.daemon = True
    thread.start()

def main():
    global args
    global adapter
    global devices
    global addresses_to_process
    global loop
    global scanner
    global timer
    global logger
    global log_level
    
    parse_options()

    logging.basicConfig(stream=sys.stderr, level=log_level)
    logger = logging.getLogger(__name__)
    
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    
    addresses_to_process = []
    devices = {}

    scanner = dbluez.Scanner(adapter, new_device_cb)
    scanner.startScan()
    
    GLib.threads_init()
    timer = GLib.timeout_add(5000, quit)
    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        logger.info('Interrupted via keyboard')

    scanner.stopScan()
    for address in devices.keys():
        try:
            devices[address].removeDevice()
        except Exception as e:
            None

    logger.info('Exit')

if __name__ == '__main__':
    main()

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

loop    = None
timer   = None
scanner = None

def usage():
    print('Usage:')
    print('  gw_dbus.py [options]')
    print('Options:')
    print('  -h, --help                Show help')
    print('  -i, --adapter=hciX        Specify local adapter interface')

def parse_options():
    global adapter
    global daemon
    
    try:
        opts, args = getopt.getopt(sys.argv[1:], "dhi:", ["help", "adapter="])
    except getopt.GetoptError as err:
        # print help information and exit:
        print(err)  # will print something like "option -a not recognized"
        usage()
        sys.exit(2)
    adapter = "hci0"
    for o, a in opts:
        if o in ('-d', '--daemon'):
            daemon = True
        elif o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o in ("-i", "--adapter"):
            adapter = a
        else:
            assert False, "unhandled option"

def new_device_cb(adapter, address, frametype, power, url):
    global devices
    logging.info('Found new device: {} with \'{}\''.format(address, url))
    if url == 'http://www.afarcloud.eu/':
        device = dbluez.Device(adapter, address, frametype, power, url)
        afcdev = parser.Thingsboard(device)
        if address not in devices.keys():
            devices[address] = afcdev
            #afcdev.startSynchronization()

def quit():
    global loop
    global scanner
    global timer

    def sync():
        GLib.source_remove(timer)

        lock = Lock()
        logging.info('Scan timeout')
        for address in devices.keys():
            lock.acquire()
            devices[address].startSynchronization(lock)


        if len(devices) > 0:
            logging.info('Waiting for sync to be finished')
            lock.acquire()
            logging.info('Sync finished')
        loop.quit()

    thread = threading.Thread(target=sync)
    thread.daemon = True
    thread.start()

def main():
    global running
    global mutex
    global args
    global adapter
    global devices
    global loop
    global scanner
    global timer
    
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
    
    parse_options()
    
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    
    devices = {}

    scanner = dbluez.Scanner(adapter, new_device_cb)
    scanner.startScan()
    
    mutex = Lock()
    GLib.threads_init()
    timer = GLib.timeout_add(5000, quit)
    loop = GLib.MainLoop()
    running = True
    try:
        loop.run()
    except KeyboardInterrupt:
        logging.info('Interrupted via keyboard')
    

    scanner.stopScan()
    for address in devices.keys():
        devices[address].removeDevice()

    running = False
    logging.info('Exit')

if __name__ == '__main__':
    main()

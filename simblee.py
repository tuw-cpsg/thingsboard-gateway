#!/usr/bin/python

import time
import socket
import sys
import os
import struct
from threading import Thread
from threading import Event
from gattlib import GATTRequester

TIMEOUT = 60000

class Requester(GATTRequester):
    def __init__(self, wakeup, *args):
        GATTRequester.__init__(self, *args)
        self.wakeup = wakeup

    def on_notification(self, handle, data):
        print(data)
        self.wakeup.set()

    def get_data(self):
        return self._data

class Device(object):
    def __init__(self, address):
        self.received = Event()
        self.requester = Requester(self.received, address, False)

        self._address = address
        self.state_connect = True

    def connect(self):
        print('Connecting to {}'.format(self._address))
        sys.stdout.flush()
        self.requester.connect(True, 'random')

    def disconnect(self):
        print('Disconnecting from {}'.format(self._address))
        self.requester.disconnect()

    def send_data(self):
        self.requester.write_by_handle(0x0012, str('\1\0'))

    def set_disconnect(self):
        self.state_connect = False

    def start(self):
        Thread(target = self.wait_notification).start()

    def wait_notification(self):
        self.connect()
        self.send_data()
        while self.state_connect:
            self.received.clear()
            if not self.received.wait(TIMEOUT):
                print 'Timeout reading from {}'.format(self._address)
                break
        self.disconnect()

    def __str__(self):
        ret = 'address:{ADDR}'.format(ADDR=self._address)
        return ret

b = Device(address)
try:
    b.start()

except KeyboardInterrupt:
    pass

except Exception as e:
    print str(e)

b.disconnect();

print('Done.')

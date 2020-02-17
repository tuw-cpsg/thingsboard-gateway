from gattlib import GATTRequester
import paho.mqtt.client as mqtt

class IBeaconDevice(GATTRequester):
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
                print('Timeout reading from {}'.format(self._address))
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
# thingsboard-gateway
Gateway to connect BLE sensors to Thingsboard.
BLE sensors are detected via Eddystene Beacon-URI.
The data is processed and formed into a JSON file compatible with the [Thingsboard MQTT Gateway API](https://thingsboard.io/docs/reference/gateway-mqtt-api/).

# Installation
The python script is based on the BlueZ D-Bus API. It prints the JSON data to `stdout` and debug information to `stderr`. The following commands executes the script pipes the output from `stdout` to `data.out`, it pipes the debug information from `stderr` to `ts` which creates a timestamp and finally stores the logging information in `gateway.log`. 
```bash
$ ./gateway.py 2>&1 >> data.out | ts "%Y-%m-%d %T" >> gateway.log
```
The content from `data.out` is piped to `mosquitto_pub` to transfer the data to a MQTT broker. The log output is piped to `ts` and stored in `mosquitto_pub.log`.
```bash
mosquitto_pub -d -h "${MQTT_HOST}" -p "${MQTT_PORT}" -t "${MQTT_TOPIC}" -u "${MQTT_USER}" -l < data.out 2>&1 | ts "%Y-%m-%d %T" >> mosquitto_pub.log
```

# Docker Image
A docker image is provided to run the following script.

## Prerequisite
```
apt-get install docker.io
```

## Installation
In order to install the gateway docker image, you need to create/modify a config file, build and run the docker image.

### Config
```
cat > config << EOF
MQTT_HOST=tba.tba.tba
MQTT_PORT=1883
MQTT_USER=TBA
MQTT_TOPIC=path/to/topic
EOF
```

### Build
```bash
docker build -t thingsboard_gateway .
```

### Run
Run it, autostart enabled:
```bash
docker run -d --env-file config --privileged -v /var/run/dbus:/var/run/dbus thingsboard_gateway:latest
```

### docker-compose
Alternatively, you can use docker-compose to build and run the docker image in the background:
```bash
docker-compose up -d
```

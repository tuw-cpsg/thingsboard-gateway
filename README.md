# thingsboard-gateway
Gateway to connect BLE sensors to Thingsboard.
BLE sensors are detected via beacon UUIDs.
The data is transmitted using MQTT to the Thingsboard server.

# Prerequisite
```
apt-get install docker.io
```

# Installation
In order to install the gateway docker image, you need to create/modify a config file, build and run the docker image.
## Config
```
cat > config << EOF
MQTT_HOST=tba.tba.tba
MQTT_PORT=1883
MQTT_PATH=path/to/publish
MQTT_USER=TBA
EOF
```
## Docker Image
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

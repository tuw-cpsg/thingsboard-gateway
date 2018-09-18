# thingsboard-gateway
Gateway to connect BLE sensors to Thingsboard.
BLE sensors are detected via beacon UUIDs.
The data is transmitted using MQTT to the Thingsboard server.

# Installation
In order to install the gateway docker image, you need to create/modify a config file, build and run the docker image.
## Config
```
cat > config.yaml << EOF
beacon:
    uuid: 12345678-1234-1234-1234-123456789abc
thingsboard:
    host: tba.tba.tba
    port: 1883
    access_token: TBA
EOF
```
## Docker Image
### Build
```
docker build -t thingsboard-gateway .
```
### Run
Run it, autostart enabled:
```
docker run --net=host --restart=always --privileged thingsboard-gateway:latest
```

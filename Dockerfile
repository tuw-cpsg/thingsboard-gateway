# https://blog.alexellis.io/getting-started-with-docker-on-raspberry-pi/
# docker run --net=host thingsboard_docker

FROM schachr/raspbian-stretch:latest
ENTRYPOINT []

RUN apt-get update && \
    apt-get -qy install\
    curl \
    ca-certificates \
    python3 python3-pip python3-requests python3-yaml python3-setuptools python3-dev \
    bluez libbluetooth-dev \
    pkg-config libglib2.0-dev libboost-thread-dev libboost-python-dev  \
    bc \
    build-essential \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

ADD pygattlib /opt/

RUN python3 -m pip install --upgrade pip
RUN python3 -m pip install pybluez paho-mqtt
RUN python3 /opt/pygattlib/setup.py build
RUN python3 /opt/pygattlib/setup.py install

ADD gateway.py /opt/thingsboard/gateway.py
ADD config.yaml /etc/thingsboard/config.yaml

CMD ["/opt/thingsboard/gateway.py"]

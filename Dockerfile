# https://blog.alexellis.io/getting-started-with-docker-on-raspberry-pi/
# docker run --net=host thingsboard_docker

FROM schachr/raspbian-stretch:latest
ENTRYPOINT []

RUN apt-get update && \
    apt-get -qy install\
    curl \
    ca-certificates \
    python python-pip python-requests python-yaml python-setuptools python-dev \
    bluez libbluetooth-dev \
    pkg-config libglib2.0-dev libboost-thread-dev libboost-python-dev  \
    bc \
    build-essential \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip
RUN pip install gattlib pybluez paho-mqtt

ADD gateway.py /opt/thingsboard/gateway.py
ADD config.yaml /etc/thingsboard/config.yaml

CMD ["/opt/thingsboard/gateway.py"]

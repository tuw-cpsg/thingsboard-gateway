# https://blog.alexellis.io/getting-started-with-docker-on-raspberry-pi/
# docker run --net=host thingsboard_docker

FROM schachr/raspbian-stretch:latest
#FROM ubuntu:18.04
ENTRYPOINT []

RUN apt-get update && \
	apt-get upgrade -y && \
    apt-get -qy install\
	gettext-base \
	dbus \
    curl \
	cron \
    moreutils \
    ca-certificates \
    python3 python3-requests python3-yaml python3-dbus python3-gi \
    bluez \
    bc \
	mosquitto-clients \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

ADD gateway.py /opt/thingsboard/gateway.py

#RUN mkdir -p /usr/lib/python3.6/dbluez
#RUN mkdir -p /usr/lib/python3.6/parser
#
#ADD dbluez.py /usr/lib/python3.6/dbluez/__init__.py
#ADD parser.py /usr/lib/python3.6/parser/__init__.py

RUN mkdir -p /usr/lib/python3.5/dbluez
RUN mkdir -p /usr/lib/python3.5/parser

ADD dbluez.py /usr/lib/python3.5/dbluez/__init__.py
ADD parser.py /usr/lib/python3.5/parser/__init__.py

RUN touch /var/log/cron.log
ADD crontab /etc/cron.d/thingsboard_gateway

CMD /bin/sh -c "envsubst < /etc/cron.d/thingsboard_gateway | crontab && /usr/sbin/cron -f"
#CMD ["/usr/sbin/cron", "-f"]

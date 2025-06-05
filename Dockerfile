FROM python:3

ARG GOWIN_VERSION
ENV GOWIN_VERSION=${GOWIN_VERSION}

WORKDIR /usr/src/gowin
ENV GOWINHOME=/usr/src/gowin

RUN curl -so gowin.tgz "https://cdn.gowinsemi.com.cn/Gowin_V${GOWIN_VERSION}_linux.tar.gz" && \
    tar -xf gowin.tgz && \
    rm gowin.tgz

RUN apt-get update && \
    apt-get install -y xxd && \
    echo "B016: EB" | xxd -r -g 0 - ${GOWINHOME}/IDE/bin/gw_sh

RUN pip install --no-cache-dir crc

WORKDIR /usr/src/apicula

CMD ["make"]

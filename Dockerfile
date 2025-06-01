FROM python:3

ARG GOWIN_VERSION
ENV GOWIN_VERSION=${GOWIN_VERSION}

WORKDIR /usr/src/gowin

RUN curl -so gowin.tgz "https://cdn.gowinsemi.com.cn/Gowin_V${GOWIN_VERSION}_linux.tar.gz" && \
    tar -xf gowin.tgz && \
    rm gowin.tgz

RUN pip install --no-cache-dir crc

WORKDIR /usr/src/apicula

ENV GOWINHOME /usr/src/gowin

CMD make

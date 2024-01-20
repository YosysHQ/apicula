FROM python:3

WORKDIR /usr/src/gowin

RUN curl -so gowin.tgz "http://cdn.gowinsemi.com.cn/Gowin_V1.9.8_linux.tar.gz" && \
    tar -xf gowin.tgz && \
    rm gowin.tgz

RUN pip install --no-cache-dir numpy crc

WORKDIR /usr/src/apicula

ENV GOWINHOME /usr/src/gowin

CMD make

FROM python:3

WORKDIR /usr/src/gowin

RUN curl -so gowin.tgz "https://cdn.gowinsemi.com.cn/Gowin_V1.9.10.03_linux.tar.gz" && \
    tar -xf gowin.tgz && \
    rm gowin.tgz

RUN pip install --no-cache-dir crc

WORKDIR /usr/src/apicula

ENV GOWINHOME /usr/src/gowin

CMD make

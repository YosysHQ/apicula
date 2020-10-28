FROM python:3

WORKDIR /usr/src/gowin

RUN mkdir -p "/root/Documents/gowinsemi/" && \
    curl -so "/root/Documents/gowinsemi/GW1N-9 Pinout.xlsx" "https://wishfulcoding.nl/gowin/UG114-1.4E_GW1N-9%20Pinout.xlsx" && \
    curl -so "/root/Documents/gowinsemi/GW1N-1 Pinout.xlsx" "https://wishfulcoding.nl/gowin/UG107-1.09E_GW1N-1%20Pinout.xlsx"

RUN curl -so gowin.tgz "http://cdn.gowinsemi.com.cn/Gowin_V1.9.3.01Beta_linux.tar.gz" && \
    tar -xf gowin.tgz && \
    rm gowin.tgz

RUN pip install --no-cache-dir numpy pandas pillow crcmod xlrd

WORKDIR /usr/src/apicula

ENV GOWINHOME /usr/src/gowin

CMD make

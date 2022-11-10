FROM python:3

WORKDIR /usr/src/gowin

RUN curl -so gowin.tgz "http://cdn.gowinsemi.com.cn/Gowin_V1.9.8_linux.tar.gz" && \
    tar -xf gowin.tgz && \
    rm gowin.tgz

RUN mkdir -p "/root/Documents/gowinsemi/" && \
    curl -so "/root/Documents/gowinsemi/GW1N-9 Pinout.xlsx" "https://wishfulcoding.nl/gowin/UG114-1.4E_GW1N-9%20Pinout.xlsx" && \
    curl -so "/root/Documents/gowinsemi/GW1NR-9 Pinout.xlsx" "https://wishfulcoding.nl/gowin/UG801-1.5E_GW1NR-9%20Pinout.xlsx" && \
    curl -so "/root/Documents/gowinsemi/GW1N-4 Pinout.xlsx" "https://wishfulcoding.nl/gowin/UG105-1.6E_GW1N-4%20Pinout.xlsx" && \
    curl -so "/root/Documents/gowinsemi/GW1N-1 Pinout.xlsx" "https://wishfulcoding.nl/gowin/UG107-1.09E_GW1N-1%20Pinout.xlsx" && \
	curl -so "/root/Documents/gowinsemi/GW1NS-2C Pinout.xlsx" "https://wishfulcoding.nl/gowin/UG825-1.2.1E_GW1NS-2C%20Pinout.xlsx" && \
	curl -so "/root/Documents/gowinsemi/GW1NS-2 Pinout.xlsx" "https://wishfulcoding.nl/gowin/UG822-1.2.1E_GW1NS-2%20Pinout.xlsx"

RUN pip install --no-cache-dir numpy crcmod

WORKDIR /usr/src/apicula

ENV GOWINHOME /usr/src/gowin

CMD make

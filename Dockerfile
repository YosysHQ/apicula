FROM python:3

WORKDIR /usr/src/gowin

RUN apt-get update && apt-get install -y curl && \
    pip install --no-cache-dir numpy pandas pillow crcmod xlrd && \
    mkdir -p "/root/Documents/gowinsemi/" && \
    curl -so "/root/Documents/gowinsemi/GW1N-9 Pinout.xlsx" "https://wishfulcoding.nl/gowin/UG114-1.4E_GW1N-9%20Pinout.xlsx" && \
    curl -so "/root/Documents/gowinsemi/GW1N-1 Pinout.xlsx" "https://wishfulcoding.nl/gowin/UG107-1.09E_GW1N-1%20Pinout.xlsx" && \
    curl -so gowin.tgz "http://cdn.gowinsemi.com.cn/Gowin_V1.9.3.01Beta_linux.tar.gz" && \
    tar -xf gowin.tgz

WORKDIR /usr/src/apicula
COPY . .

ENV GOWINHOME /usr/src/gowin
ENV ARTIFACTS /artifacts

CMD python dat19_h4x.py && \
    python tiled_fuzzer.py && \
    mkdir -p ${ARTIFACTS} && \
    cp ${DEVICE}.pickle ${ARTIFACTS}

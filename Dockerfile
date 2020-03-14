FROM python:3

WORKDIR /usr/src/gowin
ADD ["https://www.gowinsemi.com/upload/database_doc/359/document/5cf8eb7f250cf.xlsx", "/root/Documents/gowinsemi/GW1NR-9 Pinout.xlsx"]
ADD ["https://www.gowinsemi.com/upload/database_doc/186/document/5e1ff868b7434.xlsx", "/root/Documents/gowinsemi/GW1N-1 Pinout.xlsx"]
ADD http://cdn.gowinsemi.com.cn/Gowin_V1.9.3.01Beta_linux.tar.gz gowin.tgz
RUN tar -xf gowin.tgz
ENV GOWINHOME /usr/src/gowin
RUN pip install --no-cache-dir numpy pandas pillow crcmod xlrd

WORKDIR /usr/src/apicula
COPY . .

CMD python dat19_h4x.py; python tiled_fuzzer.py

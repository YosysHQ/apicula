#!/bin/bash
# usage: [BUILD_PYTHON=ON] build-npnr.sh <nextpnr-src> <apicula-src>
# Wrap in: systemd-run --user --scope -q -p MemoryMax=10G -- build-npnr.sh ...
set -e
src=$1; api=$2
mkdir -p $src/build && cd $src/build
export PYTHONPATH=$api   # chipdb generator reads this apicula revision's msgpacks
cmake .. -DARCH=himbaechel -DHIMBAECHEL_UARCH=gowin -DHIMBAECHEL_GOWIN_DEVICES="GW1N-9C;GW2A-18C;GW5A-25A" \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_PYTHON=${BUILD_PYTHON:-OFF} -DBUILD_GUI=OFF \
  -DPython3_EXECUTABLE=$HOME/code/apicula/apicula/.venv/bin/python3 > cmake.log 2>&1
make -j10 nextpnr-himbaechel > build.log 2>&1
./nextpnr-himbaechel --version

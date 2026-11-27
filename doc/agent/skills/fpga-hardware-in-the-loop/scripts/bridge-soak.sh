#!/usr/bin/env bash
# Soak-test a board's bridge firmware the way HIL CI uses it.
# Usage: bridge-soak.sh <bitstream.fs> <uart-by-id-path> <iterations> -- <openFPGALoader args...>
# e.g.   bridge-soak.sh latch.fs /dev/serial/by-id/usb-SIPEED_JTAG_Debugger_FactoryAIOT_Pro-if01-port0 20 -- -b tangnano9k
# Stops at the first failing step (load, stty, capture) so a wedged bridge is not
# reported as 20 silent failures. Output: one line per iteration, plus out<i>.bin / load<i>.log.
set -u
fs=$1 uart=$2 n=$3; shift 4
for i in $(seq 1 "$n"); do
    s=$(date +%s)
    if ! timeout 90 openFPGALoader "$@" "$fs" > "load$i.log" 2>&1; then
        echo "$i FAIL load: $(grep -iE 'error|fail|unable' "load$i.log" | head -2 | tr '\n' ' ')"; exit 1
    fi
    load_s=$(( $(date +%s) - s ))
    if ! stty -F "$uart" 115200 raw -echo 2> "stty$i.log"; then
        echo "$i FAIL stty: $(cat "stty$i.log")"; exit 1
    fi
    dd if="$uart" of=/dev/null bs=4096 iflag=nonblock 2>/dev/null
    timeout 10 cat "$uart" > "out$i.bin"
    bytes=$(wc -c < "out$i.bin")
    [ "$bytes" -eq 0 ] && { echo "$i FAIL capture: no bytes"; exit 1; }
    total=$(wc -l < "out$i.bin")
    good=$(grep -acE '^(T[0-3]:PASS|--- tick ---)$' "out$i.bin")
    echo "$i ok load=${load_s}s bytes=$bytes lines=$total bad=$((total - good))"
done

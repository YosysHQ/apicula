#!/usr/bin/env bash
# Quick HIL sanity check: load a bitstream on a bench board through the CI runner
# container and capture its UART the way examples/Makefile's hil_capture does.
#
#   hil-run.sh <tangnano9k|tangnano20k> <bitstream.fs> [settle_ticks] [reference.txt]
#
# Prints the captured tick block; with a reference, diffs against it (exit 1 on a
# difference). Not a CI substitute: lasting tests are the PR's own `hil` job.
set -euo pipefail

usage() { echo "usage: $0 <tangnano9k|tangnano20k|primer25k> <bitstream.fs> [settle_ticks] [reference.txt]" >&2; exit 2; }
[ $# -ge 2 ] || usage
# default settle = examples/Makefile's HIL_SETTLE; fewer ticks catch DSP pipelines
# before they fill (dsp-multaddalu12x12 nodes 2/3 read half their value at 5)
board=$1 fs=$2 settle=${3:-10} ref=${4:-}
[ -f "$fs" ] || { echo "no such bitstream: $fs" >&2; exit 2; }
[ -z "$ref" ] || [ -f "$ref" ] || { echo "no such reference: $ref" >&2; exit 2; }

# serial numbers and by-id paths as in examples/Makefile
loader_board=$board
case $board in
  tangnano9k)  serial=000054f5634c ;;
  tangnano20k) serial=0200 ;;
  primer25k)   serial=7c3e8265f4b7; loader_board=tangprimer25k ;;
  *) usage ;;
esac
uart=/dev/serial/by-id/usb-DirtyJTAG_DirtyJTAG_${serial}-if01

host=${HIL_HOST:-root@homeassistant.local}
port=${HIL_PORT:-22222}
container=${HIL_CONTAINER:-app_2dade7a1_github_actions_runner}
timeout_s=${HIL_TIMEOUT:-120}
# one file per call: the copy happens before the lock, so a shared name let a
# waiting caller overwrite the bitstream another caller was about to load
remote_fs=/tmp/hil-run-$board-$(uname -n)-$$.fs

# ssh joins its arguments into one remote shell line, so quote them for that shell
rexec() { ssh -o BatchMode=yes -o ConnectTimeout=10 -p "$port" "$host" "docker exec -i $container $(printf '%q ' "$@")"; }

# copy the bitstream in
rexec sh -c "cat > $remote_fs" < "$fs" || { echo "FAIL: copying the bitstream to $container" >&2; exit 3; }

# load and capture under one rig-wide lock (the BL702 bridge wedges when the other
# board loads at the same time); refuse while a CI job is running
out=$(rexec bash -s -- "$board" "$serial" "$uart" "$remote_fs" "$settle" "$timeout_s" "$loader_board" <<'EOF'
set -uo pipefail
board=$1 serial=$2 uart=$3 fs=$4 settle=$5 timeout_s=$6 loader_board=$7
trap 'rm -f "$fs"' EXIT
exec 9>/tmp/hil-run.lock
flock -n 9 || { echo "FAIL: the rig is busy with another hil-run" >&2; exit 4; }
for p in /proc/[0-9]*; do
  if tr '\0' ' ' < "$p/cmdline" 2>/dev/null | grep -q 'Runner\.Worker'; then
    echo "FAIL: a CI job is running on the runner; try again later" >&2; exit 4
  fi
done
openFPGALoader -c dirtyJtag --usb-serial-num "$serial" -b "$loader_board" "$fs" >/tmp/hil-run-$board.load.log 2>&1 \
  || { echo "FAIL: openFPGALoader (log follows)" >&2; cat /tmp/hil-run-$board.load.log >&2; exit 5; }
stty -F "$uart" 115200 raw -echo || { echo "FAIL: stty $uart" >&2; exit 6; }
dd if="$uart" of=/dev/null bs=4096 iflag=nonblock 2>/dev/null
# awk exits after the tick block and cat dies of SIGPIPE: that is the normal end
set +o pipefail
timeout "$timeout_s" cat "$uart" | awk -v n="$settle" '/--- tick ---/{c++; next} c==n{print} c==(n+1){exit}'
EOF
) || exit $?

if [ -z "$out" ]; then
  echo "FAIL: no output after $settle ticks within ${timeout_s}s" >&2; exit 7
fi
if [ -n "$ref" ]; then
  # batches print in test order, references are concatenated per test: compare sorted
  diff <(sort "$ref") <(sort <<<"$out") && echo "PASS: $(basename "$fs") on $board"
else
  printf '%s\n' "$out"
fi

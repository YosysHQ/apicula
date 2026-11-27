#!/bin/bash
# usage: sweep.sh <tag> <binary> <gw1n est|-> <gw1n pred|-> <gw2a/5a est|-> <gw2a/5a pred|-> [ripup1n ripup2a] [-- extra nextpnr args]
# Knobs are env vars read by an experiment build (GOWIN_EST/GOWIN_PRED = c,m_near,k,m_far; GOWIN_RIPUP).
tag=$1 bin=$2 e1=$3 p1=$4 e2=$5 p2=$6 r1=${7:--} r2=${8:--}
shift 8 2>/dev/null || shift $#
here=$(dirname "$0")
knobs() { # est pred ripup cmd...
    env -u GOWIN_EST -u GOWIN_PRED -u GOWIN_RIPUP \
        $([ "$1" != - ] && echo GOWIN_EST=$1) $([ "$2" != - ] && echo GOWIN_PRED=$2) $([ "$3" != - ] && echo GOWIN_RIPUP=$3) "${@:4}"
}
knobs $e1 $p1 $r1 python3 $here/bench.py $tag $bin --designs rv3-9c -j 5 -- "$@" &
knobs $e2 $p2 $r2 python3 $here/bench.py $tag $bin --designs rv7-2a,rv7-5a -j 5 -- "$@"
wait

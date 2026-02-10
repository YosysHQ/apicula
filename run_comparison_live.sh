#!/bin/bash
# Compare C++ gowin_pack output against LIVE Python gowin_pack for all examples

GOWIN_PACK="/home/user/apicula/gowin_pack_cpp/build/gowin_pack"
CHIPDB_DIR="/home/user/apicula/apycula"
EXAMPLES="/home/user/apicula/examples"

pass=0
fail=0
error=0
fail_list=""

declare -A BOARD_DEVICE
BOARD_DEVICE[tangnano20k]="GW2A-18C"
BOARD_DEVICE[primer20k]="GW2A-18"
BOARD_DEVICE[tangnano]="GW1N-1"
BOARD_DEVICE[tangnano1k]="GW1NZ-1"
BOARD_DEVICE[tangnano4k]="GW1NS-4"
BOARD_DEVICE[tangnano9k]="GW1N-9C"
BOARD_DEVICE[miniszfpga]="GW1N-9"
BOARD_DEVICE[szfpga]="GW1N-9"
BOARD_DEVICE[tec0117]="GW1N-9"
BOARD_DEVICE[runber]="GW1N-4"

for fs_file in "$EXAMPLES"/*.fs; do
    bname=$(basename "$fs_file" .fs)
    json_file="$EXAMPLES/${bname}.json"
    [ ! -f "$json_file" ] && continue

    board=""
    for b in tangnano20k primer20k tangnano1k tangnano4k tangnano9k miniszfpga szfpga tec0117 runber tangnano; do
        if [[ "$bname" == *"-$b" ]]; then board="$b"; break; fi
    done
    [ -z "$board" ] && continue

    device="${BOARD_DEVICE[$board]}"
    [ -z "$device" ] && continue
    [ ! -f "$CHIPDB_DIR/$device.msgpack.gz" ] && continue

    flags="-c"
    [[ "$bname" == emcu-* ]] && flags=""
    [[ "$board" == "tangnano4k" ]] && flags="$flags --mspi_as_gpio"
    [[ "$bname" == "pll-nanolcd-tangnano1k" ]] && flags="$flags --sspi_as_gpio --mspi_as_gpio"
    [[ "$bname" == "pll-nanolcd-tangnano9k" ]] && flags="$flags --sspi_as_gpio --mspi_as_gpio"

    py_fs="/tmp/pyfs_${bname}.fs"
    cpp_fs="/tmp/cppfs_${bname}.fs"

    # Run Python
    python3 -m apycula.gowin_pack $flags -d "$device" -o "$py_fs" "$json_file" 2>/dev/null
    if [ $? -ne 0 ]; then
        error=$((error + 1))
        fail_list="$fail_list PYERR:$bname"
        continue
    fi

    # Run C++
    if ! "$GOWIN_PACK" -d "$device" $flags -o "$cpp_fs" --chipdb "$CHIPDB_DIR/$device.msgpack.gz" "$json_file" 2>/dev/null; then
        error=$((error + 1))
        fail_list="$fail_list CPPERR:$bname"
        rm -f "$py_fs"
        continue
    fi

    if diff -q "$py_fs" "$cpp_fs" > /dev/null 2>&1; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        fail_list="$fail_list $bname"
    fi

    rm -f "$py_fs" "$cpp_fs"
done

total=$((pass + fail + error))
echo "=== C++ vs Python: $pass/$total pass, $fail fail, $error error ==="
if [ -n "$fail_list" ]; then
    echo "Failed:"
    for f in $fail_list; do
        echo "  $f"
    done
fi

#!/bin/bash
# Compare C++ gowin_pack output against Python reference for all examples

GOWIN_PACK="/home/user/apicula/gowin_pack_cpp/build/gowin_pack"
CHIPDB_DIR="/home/user/apicula/apycula"
EXAMPLES="/home/user/apicula/examples"

pass=0
fail=0
error=0
fail_list=""

# Board -> (device, extra_flags)
# Default: -c (compress)
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

# Find all .fs reference files
for fs_file in "$EXAMPLES"/*.fs; do
    bname=$(basename "$fs_file" .fs)
    json_file="$EXAMPLES/${bname}.json"

    if [ ! -f "$json_file" ]; then
        continue
    fi

    # Determine board from suffix
    board=""
    for b in tangnano20k primer20k tangnano1k tangnano4k tangnano9k miniszfpga szfpga tec0117 runber tangnano; do
        if [[ "$bname" == *"-$b" ]]; then
            board="$b"
            break
        fi
    done

    if [ -z "$board" ]; then
        continue
    fi

    device="${BOARD_DEVICE[$board]}"
    if [ -z "$device" ]; then
        continue
    fi

    chipdb="$CHIPDB_DIR/$device.msgpack.gz"
    if [ ! -f "$chipdb" ]; then
        continue
    fi

    # Build flags
    flags="-c"

    # Special cases: no compression for emcu
    if [[ "$bname" == emcu-* ]]; then
        flags=""
    fi

    # Special flags for specific boards
    if [[ "$board" == "tangnano4k" ]]; then
        flags="$flags --mspi_as_gpio"
    fi

    # Special: pll-nanolcd-tangnano1k needs --sspi_as_gpio --mspi_as_gpio
    if [[ "$bname" == "pll-nanolcd-tangnano1k" ]]; then
        flags="$flags --sspi_as_gpio --mspi_as_gpio"
    fi

    # Special: pll-nanolcd-tangnano9k needs --sspi_as_gpio --mspi_as_gpio
    if [[ "$bname" == "pll-nanolcd-tangnano9k" ]]; then
        flags="$flags --sspi_as_gpio --mspi_as_gpio"
    fi

    cpp_fs="/tmp/cpp_${bname}.fs"

    # Run C++ packer
    if ! "$GOWIN_PACK" -d "$device" $flags -o "$cpp_fs" --chipdb "$chipdb" "$json_file" 2>/dev/null; then
        error=$((error + 1))
        fail_list="$fail_list ERROR:$bname"
        continue
    fi

    # Compare
    if diff -q "$fs_file" "$cpp_fs" > /dev/null 2>&1; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        fail_list="$fail_list $bname"
    fi

    rm -f "$cpp_fs"
done

total=$((pass + fail + error))
echo "=== Results: $pass/$total pass, $fail fail, $error error ==="
echo ""
if [ -n "$fail_list" ]; then
    echo "Failed:"
    for f in $fail_list; do
        echo "  $f"
    done
fi

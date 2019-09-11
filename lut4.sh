function loop {
  cp -r lut4 lut4_$1
  cd lut4_$1
  for row in $1 $2
  do
    for col in {2..46}
    do
      for cls in {0..3}
      do
        for lut in A B
        do
          location="R${row}C${col}[${cls}][${lut}]"
          if [[ ! -f "../data/fs/$location.fs" ]]; then
            sed s/LOCATION/$location/ lut4.cst.mk > lut4.cst
            ~/bin/gowin/IDE/bin/gw_sh run.tcl
            mv impl/pnr/lut4.fs ../data/fs/$location.fs
          fi
          if [[ ! -f "../data/bits/$location.json" ]]; then
            python ../indices.py ../empty.fs ../data/fs/$location.fs > ../data/bits/$location.json
          fi
        done
      done
    done
  done
}

set -x
cd empty
~/bin/gowin/IDE/bin/gw_sh run.tcl
cd ..
cp empty/impl/pnr/empty.fs .

mkdir -p data/fs
mkdir -p data/bits
#R2C2
#R27C46
loop 2 3 &
loop 4 5 &
loop 6 7 &
loop 8 9 &
loop 10 11 &
loop 12 13 &
loop 14 15 &
loop 16 17 &
loop 18 19 &
loop 20 21 &
loop 22 23 &
loop 24 25 &
loop 26 27 &
cd ..


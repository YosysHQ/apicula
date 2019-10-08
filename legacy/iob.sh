set -x
cd empty
~/bin/gowin/IDE/bin/gw_sh run.tcl
cd ..
cp empty/impl/pnr/empty.fs .

mkdir -p data/fs
mkdir -p data/bits
cd iob
for location in {1..88}
do
  if [[ ! -f "../data/fs/pin$location.fs" ]]; then
    sed s/LOCATION/$location/ iob.cst.mk > iob.cst
    ~/bin/gowin/IDE/bin/gw_sh run.tcl
    mv impl/pnr/iob.fs ../data/fs/pin$location.fs
  fi
  if [[ ! -f "../data/bits/pin$location.json" ]]; then
    python ../indices.py ../empty.fs ../data/fs/pin$location.fs > ../data/bits/pin$location.json
  fi
done
cd ..


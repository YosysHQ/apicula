import json
import os
import subprocess
from collections import defaultdict

def build_family_aliases():
    db_hashes = defaultdict(list)
    
    family_info = defaultdict(dict)

    # load IDCODEs from programmer.json
    with open("/usr/src/gowin/IDE/bin/programmer.json") as f:
        data = json.loads(f.read())
        for device_data in data["DEVICE_CONFIG"]:
            if device_data["DEVICE"] == "JTAG_NOP":
                continue

            family_info[device_data["DEVICE"]]["idcode"] = device_data["IDCODE"]

    # if devices have the same *.fse hash, assume they are the same family
    md5_exec = subprocess.run("md5sum /usr/src/gowin/IDE/share/device/*/*.fse", 
                              shell=True, check=True, capture_output=True,
                              encoding='utf-8')

    for line in md5_exec.stdout.splitlines():
        computed_hash, path = line.split("  ")
        family = os.path.split(path)[-1].replace(".fse", "")
        db_hashes[computed_hash].append(family)

    for computed_hash, families in db_hashes.items():
        # arbitrarily use the shortest family as the "true" family
        families.sort(key=lambda x: (len(x), x))

        for family in families:
            base_family = families[0]
            family_info[family]["base_family"] = base_family

            # if the family has no IDCODE, try to inherit from the base family
            if "idcode" not in family_info[family] and "idcode" in family_info[base_family]:
                family_info[family]["idcode"] = family_info[families[0]]["idcode"]

    return family_info


if __name__ == "__main__":
    family_aliases = build_family_aliases()
    with open("family_info.json", "w") as f:
        f.write(json.dumps(dict(family_aliases), indent=2))

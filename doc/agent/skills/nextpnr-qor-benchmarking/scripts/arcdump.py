# nextpnr --post-route hook (needs BUILD_PYTHON=ON): one JSON line per routed arc
# [drv x,y,z,type,port, usr x,y,z,type,port, n_users, route_delay_ps] -> $ARCDUMP
import os, json

out = open(os.environ["ARCDUMP"], "w")
for name, net in ctx.nets:
    drv = net.driver
    if drv.cell is None or drv.cell.bel is None or net.wires is None or len(net.wires) == 0:
        continue
    dl = ctx.getBelLocation(drv.cell.bel)
    for usr in net.users:
        if usr.cell is None or usr.cell.bel is None:
            continue
        ul = ctx.getBelLocation(usr.cell.bel)
        try:
            d = ctx.getNetinfoRouteDelay(net, usr)
        except Exception:
            continue
        out.write(json.dumps([dl.x, dl.y, dl.z, str(drv.cell.type), str(drv.port),
                              ul.x, ul.y, ul.z, str(usr.cell.type), str(usr.port), len(net.users), d]) + "\n")
out.close()

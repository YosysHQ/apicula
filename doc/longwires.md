Long wires are used for fast fanout signals. The receivers can be either CLK, CE, SR or LUT inputs. 

You can figure out a lot already from the syntax of the CLOCK_LOC constraint:
 
 CLOCK_LOC "net-name" clocks=fanout [quadrant]

 clocks:
 - BUFG[0-7]  eight master clocks
 - BUFS[0-7]  eight long lines
 - LOCAL_CLOCK "not to route clock line" (???)

 fanout:
 - CLK
 - CE
 - SR set/reset/clear/preset
 - LOGIC jther than the above
 the | can be used as OR.

 So we have 8 long wires per quandrant, which btw can be set as LEFT (L), RIGHT (R) for GW1N series and as TOPLEFT (TL), TOPRIGHT (TR), BOTTOMLEFT (BT) and BOTTOMRIGHT (BR) for GW1N-9/GW1NR-9/GW1N-9C/GW1NR-9C, GW2A series.

Specifying a limit does not mean that the vendor P&R will necessarily involve a long wire. You need to play around with the number of consumers and the type of sockets. The minimum set can be represented as:
```
    name = "r_src"
    dff = codegen.Primitive("DFF", name)
    dff.portmap['CLK'] = "w_clk"
    dff.portmap['D'] = "w_dummy"
    dff.portmap['Q'] = "w_lw"
    mod.wires.update({"w_dummy", "w_lw"})
    mod.primitives[name] = dff
    cst.clocks["w_lw"] = "BUFS[5]=LOGIC"
    cst.cells[name] = "R8C12[0][A]"
    # dest ff0
    name = "r_dst0"
    dff = codegen.Primitive("DFF", name)
    dff.portmap['CLK'] = "w_clk"
    dff.portmap['D'] = "w_lw"
    dff.portmap['Q'] = "w_dst2_d"
    mod.wires.update({"w_dst2_d"})
    mod.primitives[name] = dff
    cst.cells[name] = "R2C2[0][B]"
    # dest ff2
    name = "r_dst2"
    dff = codegen.Primitive("DFFS", name)
    dff.portmap['CLK'] = "w_clk"
    dff.portmap['D'] = "w_lw"
    dff.portmap['Q'] = "w_led"
    dff.portmap['SET'] = "w_dst2_d"
    mod.primitives[name] = dff
    cst.cells[name] = "R3C3[0][B]"
```

The last thing left to add is that there are complete analogs of clock mechanisms:
LB00, LBO1,
LB0-7
LT0,1,2,4
LT13
LT00,10,20,30 and there are two things to do:

* find the connection from the spine to the T and from the DFF outputs to the spine
* teach nextpnr to use these long lines correctly.



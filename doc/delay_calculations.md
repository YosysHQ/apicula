# Calculating network delay in nextpnr

The network delay is made up of the wire and pip delays as seen in the following nextpnr code snippet:

``` C++
        while (cursor != WireId() && cursor != src_wire) {
            auto it = net_info->wires.find(cursor);


            if (it == net_info->wires.end())
                break;


            PipId pip = it->second.pip;
            if (pip == PipId())
                break;


            delay = delay + getPipDelay(pip);
            delay = delay + getWireDelay(cursor);
            cursor = getPipSrcWire(pip);
        }
```

[Context::getNetinfoRouteDelayQuad](https://github.com/YosysHQ/nextpnr/blob/764b5402e81be403658509d83950dc5ac631d29b/common/kernel/context.cc#L191-L204)

`getWireDelay` is very simple at the moment - there's no delay.

`getPipDelay` is more complicated. Let's leave aside capacitance and resistance for now and focus on where `int_delay` comes from.

``` C++
        auto &pip_data = chip_pip_info(chip_info, pip);
        auto pip_tmg = get_pip_timing(pip_data);
        if (pip_tmg != nullptr) {
            // TODO: multi corner analysis
            WireId src = getPipSrcWire(pip);			
			uint64_t input_res = fast_pip_delays ? 0 : (drive_res.count(src) ? drive_res.at(src) : 0);
			uint64_t input_cap = fast_pip_delays ? 0 : (load_cap.count(src) ? load_cap.at(src) : 0);
            auto src_tmg = get_node_timing(src);
            if (src_tmg != nullptr)
                input_res += (src_tmg->res.slow_max / 2);
            // Scale delay (fF * mOhm -> ps)
            delay_t total_delay = (input_res * input_cap) / uint64_t(1e6);
            total_delay += pip_tmg->int_delay.slow_max;


            WireId dst = getPipDstWire(pip);
            auto dst_tmg = get_node_timing(dst);
            if (dst_tmg != nullptr) {
                total_delay +=
                        ((pip_tmg->out_res.slow_max + uint64_t(dst_tmg->res.slow_max) / 2) * dst_tmg->cap.slow_max) /
                        uint64_t(1e6);
            }
			return DelayQuad(total_delay);
		}

```

Specific data like time delays we can only get from verndor's files, so let's see what we have in the database. Let's take a board like Tangano9k. We have information about speed grades copied to the chip database:

``` python
db.timing.keys()
dict_keys(['C5/I4', 'C5/I4_LV', 'C6/I5', 'C6/I5_LV', 'ES', 'ES_LV', 'A4', 'A4_LV', '8', '9', '10', '11', 'C7/I6', 'C7/I6_LV'])
```

In each grade, delays are stored by group:

``` python
ipdb> db.timing['C6/I5'].keys()
dict_keys(['lut', 'alu', 'sram', 'dff', 'bram', 'fanout', 'glbsrc', 'hclk', 'iodelay', 'wire'])
```

In each group, delays are assigned a class:

``` python
ipdb> db.timing['C6/I5']['wire'].keys()
dict_keys(['X0', 'FX1', 'X2', 'X8', 'ISB', 'X0CTL', 'X0CLK', 'X0ME'])
ipdb> db.timing['C6/I5']['wire']['X2']
[0.25999999046325684, 0.35100001096725464, 0.3630000054836273, 0.47999998927116394]
```

This quadruple number presumably stands for delays depending on the combination of edges at the input and output:

Falling->Falling, Falling->Rising, Raising->Raising, Raising->Falling.

Currently, [nextpnr](https://github.com/YosysHQ/nextpnr/blob/764b5402e81be403658509d83950dc5ac631d29b/himbaechel/uarch/gowin/gowin_arch_gen.py#L1420-L1426) collapses these four numbers into two: minimum and maximum delay, so further down in this document, when we search vendor IDE reports for delay, we shouldn't be picky about which column from FF->FR->RR->RF we take.

``` python
    def group_to_timingvalue(group):
        # if himbaechel ever recognises unateness, this should match that order.
        ff = int(group[0] * 1000)
        fr = int(group[1] * 1000)
        rr = int(group[2] * 1000)
        rf = int(group[3] * 1000)
        return TimingValue(min(ff, fr, rf, rr), max(ff, fr, rf, rr))
```

Let's especially note the `fanout` group, which will come in handy during these manipulations with capacitances and resistances:

``` python
ipdb> db.timing['C6/I5']['fanout'].keys()
dict_keys(['X0Fan', 'X1Fan', 'SX1Fan', 'X2Fan', 'X8Fan', 'FFan', 'QFan', 'OFFan', 'X0FanNum', 'X1FanNum', 'SX1FanNum', 'X2FanNum', 'X8FanNum', 'FFanNum', 'QFanNum', 'OFFanNum'])
```

# Possible interpretation of the vendor report

If you compile with IDE (from command line, in TCL script. Perhaps there is such a thing in graphical UI too, I didn't look), if you set `-gen_text_timing_rpt 1` key, then a report file will be generated, where you can see data about signal delays on different parts of the design, like this:


![IDE report fragment](fig/tNET.png)

The DELAY column is the delay value at a certain section, the exact formula is unknown, we will use a more/less plausible mechanism of turning quadruple numbers from vendor files into this single delay value.

TYPE is the type of section. Presumably tNET is wires and PIPs, tINS is primitive, tC2Q is unknown, presumably the delay between the edge on CLK to the edge on Q at DFF.

We are interested in tNET type sections.

RF - is what happens in this section, let's say FR means there will be inversion of the signal. 

NODE - name of primitive/name of port. For networks (tNETs) it's a sink.

Let's look at a simple design to understand how these quadruple numbers from the vendor files are used.

![Simple design diagram](fig/timing-ex0.png)

The highlighted network has a delay of 0.336. Let's see how we can get this. First of all, this is a `RR` section, so we will only take the third number of each quadruple.

If we unpack the image, we can see what wires are involved in this network:

`R5C15_Q0 -> R5C15_X01 -> R5C15_C2`

Why the `C2` port you ask? Unfortunately, the vendor IDE thinks it is possible to arbitrarily swap LUT inputs even after generating reports. This makes it very difficult to find patterns. So in this particular case I found where the network is connected and it is port `C2`.


Let's see what we have in the base for the `Q` and `X01`:

![Simple design investigation](fig/timing-ex1.png)

No doubt we take the third number from `wires` for `X0` - there is no getting away from this delay. For `Q` we do not have such data and it is understandable - it is the output of `DFF` and so whatever the internal delay is, it belongs to the flip-flop itself.

Next we have fanout data, but in pure `QFan` and `X0Fan` are too large - remember we have 0.336 in the report, now we have already gained 0.3269999921321869 due to the internal delay of `X0`.



Let's assume that `QFan` and `X0Fan` are the maximum delay provided that all `QFanNum` and `X0FanNum` wires are connected respectively, then we can use only a small part of this delay - proportional to the wires connected.



In our case, only one wire out of 24 for `Q` and one wire out of 22 for `X0` are used:

```
delay = 1/QFanNum * QFan + 0.3269999921321869 + 1/X0FanNum * X0Fan
delay = 1/24 * QFan + 0.3269999921321869 + 1/22 * X0Fan
delay = 1/24 * 0.03750000149011612 + 0.3269999921321869 + 1/22 * 0.1616666615009308
delay = 0.33591097680795373
```

I'd say in this case we've pretty much guessed the formula. Now we can move on to comparing nextpnr's calculations with the vendor's report, given our knowledge of how the total network delay is obtained.



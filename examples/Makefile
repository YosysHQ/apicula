YOSYS ?= yosys
NEXTPNR ?= nextpnr-himbaechel
NEXTPNR_FLAGS ?= --timing-allow-fail -r
YOSYS_FLAGS = -setundef

# registers in IO blocks
ioregs-%.json: NEXTPNR_FLAGS += --vopt ireg_in_iob --vopt oreg_in_iob

# Hardware-in-the-loop batches, see the HIL section below. The DSP tests do
# not fit in one batch, and nextpnr places far fewer of them together than the
# DSP macros would hold (GW1N-9 has 5, GW2A-18 12). These were found by trying.
HIL_BATCH_gw1n9-a := latch dsp-multalu36x18 dsp-multalu18x18
HIL_BATCH_gw1n9-b := dsp-mult36x36 dsp-multaddalu18x18
HIL_BATCH_gw1n9-c := dsp-alu54d dsp-mult18x18
HIL_BATCH_gw1n9-d := dsp-padd18 dsp-mult9x9
HIL_BATCH_gw1n9-e := dsp-padd9
# Clock tests: nextpnr runs out of global clock routing with clkdiv and the
# others together, and crashes on dhcen next to dqce or dcs.
HIL_BATCH_gw1n9-clk-a := osc dqce dcs rpll
HIL_BATCH_gw1n9-clk-b := clkdiv
# BSRAM: GW1N-9C has 26 blocks, each test takes four.
HIL_BATCH_gw1n9-bsram-a := bsram-rom bsram-rom2 bsram-sp2
HIL_BATCH_gw1n9-bsram-b := bsram-sdp2 bsram-dp
# userflash is in no batch: every load erases a flash page (10,000 cycles).
# Run it alone, as make hil-userflash-tangnano9k.
HIL_BATCHES_tangnano9k := gw1n9-a gw1n9-b gw1n9-c gw1n9-d gw1n9-e \
	gw1n9-clk-a gw1n9-clk-b gw1n9-bsram-a gw1n9-bsram-b
# Known broken, in no batch; make hil-tangnano9k-broken runs them.
# dhcen: #648. bsram-sp, bsram-dp16, bsram-sdp: byte enables, #652.
HIL_BROKEN_tangnano9k := dhcen bsram-sp bsram-dp16 bsram-sdp

HIL_BATCH_gw2a-a := latch dsp-mult36x36 dsp-multalu36x18 dsp-multalu18x18 dsp-multaddalu18x18
HIL_BATCH_gw2a-b := dsp-alu54d dsp-mult9x9 dsp-padd9 dsp-padd18
# Alone, so its SOA chain starts inside a DSP macro: on GW2A the cascade from
# the first multiplier breaks when nextpnr puts it across a macro boundary.
HIL_BATCH_gw2a-c := dsp-mult18x18
HIL_BATCH_gw2a-clk-a := osc dqce dcs rpll
HIL_BATCH_gw2a-clk-b := clkdiv
HIL_BATCH_gw2a-clk-c := dhcen
HIL_BATCH_gw2a-bsram := bsram-rom bsram-rom2 bsram-sp bsram-sp2 bsram-sdp2 bsram-dp bsram-dp16
HIL_BATCHES_tangnano20k := gw2a-a gw2a-b gw2a-c gw2a-clk-a gw2a-clk-b gw2a-clk-c gw2a-bsram
# Known broken, in no batch; make hil-tangnano20k-broken runs them.
# bsram-sdp: SDPX9B byte enables fail at some BSRAM sites, #647.
# *-bugs: the BSRAM failures of #649; bsram-dp-bugs crashes nextpnr, #650.
HIL_BROKEN_tangnano20k := bsram-sdp bsram-rom-bugs bsram-sp-bugs bsram-sdp-bugs bsram-dp-bugs

HIL_BATCH_gw5a-a := latch lut8 alu rom16 big-shift osc
# The clock tests each alone: with too many PLL clocks on global wires (plla
# and dcs together, or all seven PLLA outputs in one test) nextpnr routes the
# system clock partly through the fabric in some placements, and the reporter
# garbles its output; with osc and plla it sometimes fails to route the
# oscillator.
HIL_BATCH_gw5a-clk-a := plla
HIL_BATCH_gw5a-clk-b := dcs
HIL_BATCH_gw5a-clk-c := plla2
HIL_BATCH_gw5a-bsram := bsram-rom bsram-rom2 bsram-sp bsram-sp2 bsram-sdp bsram-sdp2 bsram-dp bsram-dp16 \
	bsram-rom-bugs bsram-sp-bugs bsram-sdp-bugs bsram-dp-bugs
HIL_BATCH_gw5a-dsp := dsp-mult12x12 dsp-multaddalu12x12 dsp-multalu27x18 dsp-mult27x36
HIL_BATCHES_primer25k := gw5a-a gw5a-clk-a gw5a-clk-b gw5a-clk-c gw5a-bsram gw5a-dsp
# The other GW5A boards are not on a bench: build-only, from gw5a/Makefile.
# GW5AT-60B: nextpnr asserts on dcs ("No clock inputs"), cannot place
# dsp-mult27x36, and fails to route the BSRAM inputs of six bsram tests
# together, so those build one by one, and of bsram-sp-bugs alone in most
# placements. GW5AST-138C has neither OSCA nor PLLA,
# and gowin_pack has no MULTALU27X18 for it. None of these boards had a dcs or
# DSP example before.
HIL_BATCH_gw5ast-a := latch lut8 alu rom16 big-shift
HIL_BATCHES_tangconsole60k := gw5a-a gw5a-clk-a gw5a-clk-c \
	bsram-rom bsram-rom2 bsram-sp bsram-sp2 bsram-sdp bsram-sdp2 bsram-dp bsram-dp16 \
	bsram-rom-bugs bsram-sdp-bugs bsram-dp-bugs
HIL_BATCHES_tangmega138k := gw5ast-a gw5a-bsram
HIL_BATCHES_tangconsole138k := gw5ast-a gw5a-bsram

.DEFAULT_GOAL := all

.PHONY: all tangnano20k primer20k tangnano tangnano1k tangnano4k tangnano9k szfpga tec0117 runber
.PHONY: unpacked tangnano20k-unpacked primer20k-unpacked tangnano-unpacked tangnano1k-unpacked
.PHONY: tangnano4k-unpacked tangnano9k-unpacked szfpga-unpacked tec0117-unpacked runber-unpacked
.PHONY: clean

tangnano20k: \
	blinky-tangnano20k.fs shift-tangnano20k.fs blinky-tbuf-tangnano20k.fs blinky-oddr-tangnano20k.fs \
	tlvds-tangnano20k.fs elvds-tangnano20k.fs oddr-tlvds-tangnano20k.fs dvi-example-tangnano20k.fs \
	oddr-elvds-tangnano20k.fs pll-nanolcd-tangnano20k.fs attosoc-tangnano20k.fs \
	oser4-tangnano20k.fs ovideo-tangnano20k.fs oser8-tangnano20k.fs oser10-tangnano20k.fs \
	iddr-tangnano20k.fs iddrc-tangnano20k.fs iodelay-tangnano20k.fs \
	ides4-tangnano20k.fs ivideo-tangnano20k.fs ides8-tangnano20k.fs ides10-tangnano20k.fs \
	femto-riscv-memtest-tangnano20k.fs \
	femto-riscv-15-tangnano20k.fs femto-riscv-16-tangnano20k.fs femto-riscv-18-tangnano20k.fs \
	femto-riscv-18-test-tangnano20k.fs \
	ioregs-tangnano20k.fs \
	$(HIL_BATCHES_tangnano20k:%=hil-%-tangnano20k.fs)

primer20k: \
	blinky-primer20k.fs shift-primer20k.fs blinky-tbuf-primer20k.fs blinky-oddr-primer20k.fs \
	hil-osc-primer20k.fs tlvds-primer20k.fs elvds-primer20k.fs oddr-tlvds-primer20k.fs \
	hil-clkdiv-primer20k.fs dvi-example-primer20k.fs hil-dhcen-primer20k.fs \
	oddr-elvds-primer20k.fs pll-nanolcd-primer20k.fs attosoc-primer20k.fs \
	oser4-primer20k.fs ovideo-primer20k.fs oser8-primer20k.fs oser10-primer20k.fs \
	iddr-primer20k.fs iddrc-primer20k.fs iodelay-primer20k.fs \
	ides4-primer20k.fs ivideo-primer20k.fs ides8-primer20k.fs ides10-primer20k.fs \
	hil-bsram-rom-primer20k.fs hil-bsram-sp-primer20k.fs hil-bsram-sdp-primer20k.fs hil-bsram-dp-primer20k.fs \
	femto-riscv-15-primer20k.fs femto-riscv-16-primer20k.fs femto-riscv-18-primer20k.fs \
	hil-dsp-mult18x18-primer20k.fs hil-dsp-mult36x36-primer20k.fs hil-dsp-padd9-primer20k.fs hil-dsp-padd18-primer20k.fs \
	hil-dsp-mult9x9-primer20k.fs hil-dsp-alu54d-primer20k.fs hil-dsp-multalu18x18-primer20k.fs \
	hil-dsp-multalu36x18-primer20k.fs hil-dsp-multaddalu18x18-primer20k.fs \
	hil-dqce-primer20k.fs hil-dcs-primer20k.fs \
	ioregs-primer20k.fs

tangnano: \
	blinky-tangnano.fs shift-tangnano.fs blinky-tbuf-tangnano.fs blinky-oddr-tangnano.fs \
	hil-osc-tangnano.fs elvds-tangnano.fs oddr-elvds-tangnano.fs pll-nanolcd-tangnano.fs \
	hil-clkdiv-tangnano.fs hil-dhcen-tangnano.fs \
	oser4-tangnano.fs ovideo-tangnano.fs oser8-tangnano.fs oser10-tangnano.fs \
	iddr-tangnano.fs iddrc-tangnano.fs iodelay-tangnano.fs \
	ides4-tangnano.fs ivideo-tangnano.fs ides8-tangnano.fs ides10-tangnano.fs \
	hil-bsram-rom-tangnano.fs hil-bsram-sp-tangnano.fs hil-bsram-sdp-tangnano.fs hil-bsram-dp-tangnano.fs \
	ioregs-tangnano.fs

tangnano1k: \
	blinky-tangnano1k.fs shift-tangnano1k.fs blinky-tbuf-tangnano1k.fs blinky-oddr-tangnano1k.fs \
	hil-osc-tangnano1k.fs elvds-tangnano1k.fs oddr-elvds-tangnano1k.fs pll-nanolcd-tangnano1k.fs \
	hil-clkdiv-tangnano1k.fs hil-dhcen-tangnano1k.fs \
	oser4-tangnano1k.fs ovideo-tangnano1k.fs oser8-tangnano1k.fs oser10-tangnano1k.fs \
	iddr-tangnano1k.fs iddrc-tangnano1k.fs iodelay-tangnano1k.fs \
	ides4-tangnano1k.fs ivideo-tangnano1k.fs ides8-tangnano1k.fs ides10-tangnano1k.fs \
	hil-bsram-rom-tangnano1k.fs hil-bsram-sp-tangnano1k.fs hil-bsram-sdp-tangnano1k.fs hil-bsram-dp16-tangnano1k.fs \
	hil-dqce-tangnano1k.fs hil-dcs-tangnano1k.fs hil-userflash-tangnano1k.fs bandgap-tangnano1k.fs \
	ioregs-tangnano1k.fs

tangnano4k: \
	blinky-tangnano4k.fs shift-tangnano4k.fs blinky-tbuf-tangnano4k.fs blinky-oddr-tangnano4k.fs \
	hil-osc-tangnano4k.fs tlvds-tangnano4k.fs elvds-tangnano4k.fs oddr-tlvds-tangnano4k.fs \
	hil-clkdiv-tangnano4k.fs hil-dhcen-tangnano4k.fs \
	oddr-elvds-tangnano4k.fs hil-pllvr-tangnano4k.fs oser16-tangnano4k.fs \
	oser4-tangnano4k.fs ovideo-tangnano4k.fs oser8-tangnano4k.fs oser10-tangnano4k.fs \
	iddr-tangnano4k.fs iddrc-tangnano4k.fs ides16-tangnano4k.fs \
	ides4-tangnano4k.fs ivideo-tangnano4k.fs ides8-tangnano4k.fs ides10-tangnano4k.fs \
	oser10-tlvds-tangnano4k.fs iodelay-tangnano4k.fs mipi-out-tangnano4k.fs femto-riscv-memtest-tangnano4k.fs \
	femto-riscv-15-tangnano4k.fs femto-riscv-16-tangnano4k.fs femto-riscv-18-tangnano4k.fs \
	hil-dsp-mult18x18-tangnano4k.fs hil-dsp-mult36x36-tangnano4k.fs hil-dsp-padd9-tangnano4k.fs hil-dsp-padd18-tangnano4k.fs \
	hil-dsp-mult9x9-tangnano4k.fs hil-dsp-alu54d-tangnano4k.fs hil-dsp-multalu18x18-tangnano4k.fs \
	hil-dsp-multalu36x18-tangnano4k.fs hil-dsp-multaddalu18x18-tangnano4k.fs \
	hil-dqce-tangnano4k.fs hil-dcs-tangnano4k.fs emcu-blinky-tangnano4k.fs emcu-with-apb-blinky-tangnano4k.fs \
	emcu-with-apb-spi-tangnano4k.fs i3c-tangnano4k.fs mipi-out-tangnano4k.fs \
	ioregs-tangnano4k.fs

tangnano9k: \
	blinky-tangnano9k.fs shift-tangnano9k.fs blinky-tbuf-tangnano9k.fs blinky-oddr-tangnano9k.fs \
	dvi-example-tangnano9k.fs tlvds-tangnano9k.fs elvds-tangnano9k.fs oddr-tlvds-tangnano9k.fs \
	oddr-elvds-tangnano9k.fs pll-nanolcd-tangnano9k.fs oser16-tangnano9k.fs attosoc-tangnano9k.fs \
	oser4-tangnano9k.fs ovideo-tangnano9k.fs oser8-tangnano9k.fs oser10-tangnano9k.fs \
	iddr-tangnano9k.fs iddrc-tangnano9k.fs iodelay-tangnano9k.fs mipi-out-tangnano4k.fs \
	ides4-tangnano9k.fs ivideo-tangnano9k.fs ides8-tangnano9k.fs ides10-tangnano9k.fs \
	oser10-elvds-tangnano9k.fs femto-riscv-memtest-tangnano9k.fs \
	femto-riscv-15-tangnano9k.fs femto-riscv-16-tangnano9k.fs femto-riscv-18-tangnano9k.fs \
	hil-userflash-tangnano9k.fs i3c-tangnano9k.fs mipi-tangnano9k.fs mipi-out-tangnano9k.fs \
	femto-riscv-18-test-tangnano9k.fs \
	ioregs-tangnano9k.fs \
	$(HIL_BATCHES_tangnano9k:%=hil-%-tangnano9k.fs)

szfpga: \
	blinky-szfpga.fs shift-szfpga.fs blinky-tbuf-szfpga.fs blinky-oddr-szfpga.fs \
	hil-osc-szfpga.fs tlvds-szfpga.fs elvds-szfpga.fs oddr-tlvds-szfpga.fs \
	hil-clkdiv-szfpga.fs hil-dhcen-szfpga.fs \
	oddr-elvds-szfpga.fs hil-rpll-szfpga.fs oser16-szfpga.fs attosoc-szfpga.fs \
	oser4-szfpga.fs ovideo-szfpga.fs oser8-szfpga.fs oser10-szfpga.fs \
	iddr-szfpga.fs iddrc-szfpga.fs ides16-szfpga.fs iodelay-szfpga.fs \
	ides4-szfpga.fs ivideo-szfpga.fs ides8-szfpga.fs ides10-szfpga.fs \
	hil-bsram-rom-szfpga.fs hil-bsram-sp-szfpga.fs hil-bsram-sdp-szfpga.fs \
	femto-riscv-15-szfpga.fs femto-riscv-16-szfpga.fs femto-riscv-18-szfpga.fs \
	hil-dsp-mult18x18-szfpga.fs hil-dsp-mult36x36-szfpga.fs hil-dsp-padd9-szfpga.fs hil-dsp-padd18-szfpga.fs \
	hil-dsp-mult9x9-szfpga.fs hil-dsp-alu54d-szfpga.fs hil-dsp-multalu18x18-szfpga.fs \
	hil-dsp-multalu36x18-szfpga.fs hil-dsp-multaddalu18x18-szfpga.fs

tec0117: \
	blinky-tec0117.fs shift-tec0117.fs blinky-tbuf-tec0117.fs blinky-oddr-tec0117.fs \
	hil-osc-tec0117.fs tlvds-tec0117.fs elvds-tec0117.fs oddr-tlvds-tec0117.fs \
	hil-clkdiv-tec0117.fs hil-dhcen-tec0117.fs \
	oddr-elvds-tec0117.fs hil-rpll-tec0117.fs oser16-tec0117.fs attosoc-tec0117.fs \
	oser4-tec0117.fs ovideo-tec0117.fs oser8-tec0117.fs oser10-tec0117.fs \
	iddr-tec0117.fs iddrc-tec0117.fs ides16-tec0117.fs iodelay-tec0117.fs \
	ides4-tec0117.fs ivideo-tec0117.fs ides8-tec0117.fs ides10-tec0117.fs \
	hil-dsp-mult18x18-tec0117.fs hil-dsp-mult36x36-tec0117.fs hil-dsp-padd9-tec0117.fs hil-dsp-padd18-tec0117.fs \
	hil-dsp-mult9x9-tec0117.fs hil-dsp-alu54d-tec0117.fs hil-dsp-multalu18x18-tec0117.fs \
	hil-dsp-multalu36x18-tec0117.fs hil-dsp-multaddalu18x18-tec0117.fs \
	femto-riscv-18-test-tec0117.fs \
	hil-latch-tec0117.fs \
	ioregs-tec0117.fs

runber: \
	blinky-runber.fs shift-runber.fs blinky-tbuf-runber.fs blinky-oddr-runber.fs \
	hil-osc-runber.fs tlvds-runber.fs elvds-runber.fs oddr-tlvds-runber.fs \
	hil-clkdiv-runber.fs \
	oddr-elvds-runber.fs hil-rpll-runber.fs \
	oser4-runber.fs ovideo-runber.fs oser8-runber.fs oser10-runber.fs \
	iddr-runber.fs iddrc-runber.fs iodelay-runber.fs \
	ides4-runber.fs ivideo-runber.fs ides8-runber.fs ides10-runber.fs \
	hil-dsp-mult36x36-runber.fs hil-dsp-padd9-runber.fs hil-dsp-padd18-runber.fs \
	hil-dsp-mult9x9-runber.fs hil-dsp-alu54d-runber.fs hil-dsp-multalu18x18-runber.fs \
	hil-dsp-multalu36x18-runber.fs hil-dsp-multaddalu18x18-runber.fs \
	ioregs-runber.fs

all: tangnano20k primer20k tangnano tangnano1k tangnano4k tangnano9k szfpga tec0117 runber

tangnano20k-unpacked: \
	blinky-tangnano20k-unpacked.v shift-tangnano20k-unpacked.v \
	blinky-tbuf-tangnano20k-unpacked.v blinky-oddr-tangnano20k-unpacked.v \
	hil-gw2a-clk-a-tangnano20k-unpacked.v tlvds-tangnano20k-unpacked.v \
	elvds-tangnano20k-unpacked.v oddr-tlvds-tangnano20k-unpacked.v \
	oddr-elvds-tangnano20k-unpacked.v pll-nanolcd-tangnano20k-unpacked.v \
	attosoc-tangnano20k-unpacked.v oser4-tangnano20k-unpacked.v ovideo-tangnano20k-unpacked.v \
	oser8-tangnano20k-unpacked.v oser10-tangnano20k-unpacked.v \
	ides4-tangnano20k-unpacked.v ivideo-tangnano20k-unpacked.v ides8-tangnano20k-unpacked.v \
	ides10-tangnano20k-unpacked.v \
	hil-bsram-rom-tangnano20k-unpacked.v hil-bsram-sp-tangnano20k-unpacked.v hil-bsram-sdp-tangnano20k-unpacked.v hil-bsram-dp-tangnano20k-unpacked.v \
	femto-riscv-15-tangnano20k-unpacked.v femto-riscv-16-tangnano20k-unpacked.v femto-riscv-18-tangnano20k-unpacked.v

primer20k-unpacked: \
	blinky-primer20k-unpacked.v shift-primer20k-unpacked.v blinky-tbuf-primer20k-unpacked.v \
	blinky-oddr-primer20k-unpacked.v hil-osc-primer20k-unpacked.v tlvds-primer20k-unpacked.v \
	elvds-primer20k-unpacked.v oddr-tlvds-primer20k-unpacked.v \
	oddr-elvds-primer20k-unpacked.v pll-nanolcd-primer20k-unpacked.v attosoc-primer20k-unpacked.v \
	oser4-primer20k-unpacked.v ovideo-primer20k-unpacked.v oser8-primer20k-unpacked.v \
	oser10-primer20k-unpacked.v ides4-primer20k-unpacked.v ivideo-primer20k-unpacked.v \
	ides8-primer20k-unpacked.v ides10-primer20k-unpacked.v \
	hil-bsram-rom-primer20k-unpacked.v hil-bsram-sp-primer20k-unpacked.v hil-bsram-sdp-primer20k-unpacked.v hil-bsram-dp-primer20k-unpacked.v \
	femto-riscv-15-primer20k-unpacked.v femto-riscv-16-primer20k-unpacked.v femto-riscv-18-primer20k-unpacked.v

tangnano-unpacked: \
	blinky-tangnano-unpacked.v shift-tangnano-unpacked.v blinky-tbuf-tangnano-unpacked.v \
	blinky-oddr-tangnano-unpacked.v hil-osc-tangnano-unpacked.v elvds-tangnano-unpacked.v \
	oddr-elvds-tangnano-unpacked.v pll-nanolcd-tangnano-unpacked.v \
	oser4-tangnano-unpacked.v ovideo-tangnano-unpacked.v oser8-tangnano-unpacked.v \
	oser10-tangnano-unpacked.v ides4-tangnano-unpacked.v ivideo-tangnano-unpacked.v \
	ides8-tangnano-unpacked.v ides10-tangnano-unpacked.v \
	hil-bsram-rom-tangnano-unpacked.v hil-bsram-sp-tangnano-unpacked.v hil-bsram-sdp-tangnano-unpacked.v hil-bsram-dp-tangnano-unpacked.v

tangnano1k-unpacked: \
	blinky-tangnano1k-unpacked.v shift-tangnano1k-unpacked.v blinky-tbuf-tangnano1k-unpacked.v \
	blinky-oddr-tangnano1k-unpacked.v hil-osc-tangnano1k-unpacked.v elvds-tangnano1k-unpacked.v \
	oddr-elvds-tangnano1k-unpacked.v pll-nanolcd-tangnano1k-unpacked.v oser4-tangnano1k-unpacked.v \
	ovideo-tangnano1k-unpacked.v oser8-tangnano1k-unpacked.v oser10-tangnano1k-unpacked.v \
	ides4-tangnano1k-unpacked.v ivideo-tangnano1k-unpacked.v ides8-tangnano1k-unpacked.v \
	ides10-tangnano1k-unpacked.v \
	hil-bsram-rom-tangnano1k-unpacked.v hil-bsram-sp-tangnano1k-unpacked.v hil-bsram-sdp-tangnano1k-unpacked.v hil-bsram-dp16-tangnano1k-unpacked.v

tangnano4k-unpacked: \
	blinky-tangnano4k-unpacked.v shift-tangnano4k-unpacked.v blinky-tbuf-tangnano4k-unpacked.v \
	blinky-oddr-tangnano4k-unpacked.v hil-osc-tangnano4k-unpacked.v tlvds-tangnano4k-unpacked.v \
	elvds-tangnano4k-unpacked.v oddr-tlvds-tangnano4k-unpacked.v oddr-elvds-tangnano4k-unpacked.v \
	hil-pllvr-tangnano4k-unpacked.v oser16-tangnano4k-unpacked.v oser4-tangnano4k-unpacked.v \
	ovideo-tangnano4k-unpacked.v oser8-tangnano4k-unpacked.v oser10-tangnano4k-unpacked.v \
	ides16-tangnano4k-unpacked.v ides4-tangnano4k-unpacked.v ivideo-tangnano4k-unpacked.v \
	ides8-tangnano4k-unpacked.v ides10-tangnano4k-unpacked.v oser10-tlvds-tangnano4k-unpacked.v \
	femto-riscv-15-tangnano4k-unpacked.v femto-riscv-16-tangnano4k-unpacked.v femto-riscv-18-tangnano4k-unpacked.v

tangnano9k-unpacked: \
	blinky-tangnano9k-unpacked.v shift-tangnano9k-unpacked.v blinky-tbuf-tangnano9k-unpacked.v \
	blinky-oddr-tangnano9k-unpacked.v hil-gw1n9-clk-a-tangnano9k-unpacked.v tlvds-tangnano9k-unpacked.v \
	elvds-tangnano9k-unpacked.v oddr-tlvds-tangnano9k-unpacked.v oddr-elvds-tangnano9k-unpacked.v \
	pll-nanolcd-tangnano9k-unpacked.v oser16-tangnano9k-unpacked.v attosoc-tangnano9k-unpacked.v \
	oser4-tangnano9k-unpacked.v ovideo-tangnano9k-unpacked.v oser8-tangnano9k-unpacked.v \
	oser10-tangnano9k-unpacked.v ides4-tangnano9k-unpacked.v ivideo-tangnano9k-unpacked.v \
	ides8-tangnano9k-unpacked.v ides10-tangnano9k-unpacked.v \
	hil-bsram-rom-tangnano9k-unpacked.v hil-bsram-sp-tangnano9k-unpacked.v hil-bsram-sdp-tangnano9k-unpacked.v hil-bsram-dp-tangnano9k-unpacked.v \
	femto-riscv-15-tangnano9k-unpacked.v femto-riscv-16-tangnano9k-unpacked.v femto-riscv-18-tangnano9k-unpacked.v

szfpga-unpacked: \
	blinky-szfpga-unpacked.v shift-szfpga-unpacked.v blinky-tbuf-szfpga-unpacked.v \
	blinky-oddr-szfpga-unpacked.v hil-osc-szfpga-unpacked.v tlvds-szfpga-unpacked.v \
	elvds-szfpga-unpacked.v oddr-tlvds-szfpga-unpacked.v oddr-elvds-szfpga-unpacked.v \
	hil-rpll-szfpga-unpacked.v oser16-szfpga-unpacked.v attosoc-szfpga-unpacked.v \
	oser4-szfpga-unpacked.v ovideo-szfpga-unpacked.v oser8-szfpga-unpacked.v \
	oser10-szfpga-unpacked.v ides16-szfpga-unpacked.v ides4-szfpga-unpacked.v \
	ivideo-szfpga-unpacked.v ides8-szfpga-unpacked.v ides10-szfpga-unpacked.v \
	hil-bsram-rom-szfpga-unpacked.v hil-bsram-sp-szfpga-unpacked.v hil-bsram-sdp-szfpga-unpacked.v \
	femto-riscv-15-szfpga-unpacked.v femto-riscv-16-szfpga-unpacked.v femto-riscv-18-szfpga-unpacked.v

tec0117-unpacked: \
	blinky-tec0117-unpacked.v shift-tec0117-unpacked.v blinky-tbuf-tec0117-unpacked.v \
	blinky-oddr-tec0117-unpacked.v hil-osc-tec0117-unpacked.v tlvds-tec0117-unpacked.v \
	elvds-tec0117-unpacked.v oddr-tlvds-tec0117-unpacked.v oddr-elvds-tec0117-unpacked.v \
	hil-rpll-tec0117-unpacked.v oser16-tec0117-unpacked.v attosoc-tec0117-unpacked.v \
	oser4-tec0117-unpacked.v ovideo-tec0117-unpacked.v oser8-tec0117-unpacked.v \
	oser10-tec0117-unpacked.v ides16-tec0117-unpacked.v ides4-tec0117-unpacked.v \
	ivideo-tec0117-unpacked.v ides8-tec0117-unpacked.v ides10-tec0117-unpacked.v \
	femto-riscv-15-tangnano9k-unpacked.v femto-riscv-16-tangnano9k-unpacked.v femto-riscv-18-tangnano9k-unpacked.v

runber-unpacked: \
	blinky-runber-unpacked.v shift-runber-unpacked.v blinky-tbuf-runber-unpacked.v \
	blinky-oddr-runber-unpacked.v hil-osc-runber-unpacked.v tlvds-runber-unpacked.v \
	elvds-runber-unpacked.v oddr-tlvds-runber-unpacked.v oddr-elvds-runber-unpacked.v \
	hil-rpll-runber-unpacked.v oser4-runber-unpacked.v ovideo-runber-unpacked.v \
	oser8-runber-unpacked.v oser10-runber-unpacked.v ides4-runber-unpacked.v \
	ivideo-runber-unpacked.v ides8-runber-unpacked.v ides10-runber-unpacked.v

unpacked: tangnano20k-unpacked primer20k-unpacked tangnano-unpacked tangnano1k-unpacked \
	tangnano4k-unpacked tangnano9k-unpacked szfpga-unpacked tec0117-unpacked runber-unpacked

clean:
	rm -f *.json *.fs *-unpacked.v hil-*.v hil-*.out

# ============================================================
# Hardware-in-the-loop tests
#
# The tests live in hil.v. A batch is one bitstream with a set of them enabled
# (HIL_BATCH_* at the top), so it costs one place-and-route and one upload.
# Every test is also a batch of its own: when a batch fails as a whole, run its
# tests one by one, e.g.
#   make hil-dsp-padd9-tangnano9k
# Each test has a reference in hil-references/; a batch expects the lines of
# its tests' references. Every line names its test, so the order is ignored.
hil_tests = $(or $(HIL_BATCH_$(1)),$(1))

# Written to a temporary file first: the GW5A boards' builds from gw5a/Makefile
# run as separate make processes that can write the same wrapper at once.
hil-%.v: hil.v $(wildcard hil/*.v) emitter_uart.v
	{ printf '`define HIL_%s\n' $(subst -,_,$(call hil_tests,$*)); echo '`include "hil.v"'; } > $@.$$$$ && \
	mv $@.$$$$ $@

# Keep the bitstreams of single tests, which no board target lists
.PRECIOUS: %-tangnano9k.fs %-tangnano20k.fs %-primer25k.fs

HIL_SETTLE ?= 10
HIL_TIMEOUT ?= 120
# $(call hil_capture,UART_DEVICE_PATH)
define hil_capture
stty -F $(1) 115200 raw -echo && \
dd if=$(1) of=/dev/null bs=4096 iflag=nonblock 2>/dev/null; \
timeout $(HIL_TIMEOUT) cat $(1) | \
awk -v n=$(HIL_SETTLE) '/--- tick ---/{c++; next} c==n{print} c==(n+1){exit}'
endef

# $(call hil_check,BATCH,BOARD,USB_SERIAL[,LOADER_BOARD]); LOADER_BOARD is
# openFPGALoader's name for the board when it differs from ours
define hil_check
openFPGALoader -c dirtyJtag --usb-serial-num $(3) -b $(or $(4),$(2)) hil-$(1)-$(2).fs
$(call hil_capture,/dev/serial/by-id/usb-DirtyJTAG_DirtyJTAG_$(3)-if01) | sort > hil-$(1)-$(2).out
sort $(patsubst %,hil-references/%.txt,$(call hil_tests,$(1))) | diff - hil-$(1)-$(2).out
@echo "PASS: $(1) ($(2))"
endef

# $(call hil_femto,BOARD,USB_SERIAL)
define hil_femto
openFPGALoader -c dirtyJtag --usb-serial-num $(2) -b $(1) femto-riscv-18-test-$(1).fs
$(call hil_capture,/dev/serial/by-id/usb-DirtyJTAG_DirtyJTAG_$(2)-if01) | diff hil-references/femto-riscv-18-test.txt -
@echo "PASS: femto-riscv-18-test ($(1))"
endef
hil-femto-riscv-18-test-%: HIL_SETTLE = 1

# --- tangnano9k (GW1N-9C) ---
hil-%-tangnano9k: hil-%-tangnano9k.fs
	$(call hil_check,$*,tangnano9k,000054f5634c)

hil-femto-riscv-18-test-tangnano9k: femto-riscv-18-test-tangnano9k.fs
	$(call hil_femto,tangnano9k,000054f5634c)

.PHONY: hil-tangnano9k
hil-tangnano9k: $(HIL_BATCHES_tangnano9k:%=hil-%-tangnano9k) hil-femto-riscv-18-test-tangnano9k

# --- tangnano20k (GW2A-18C) ---
hil-%-tangnano20k: hil-%-tangnano20k.fs
	$(call hil_check,$*,tangnano20k,0200)

hil-femto-riscv-18-test-tangnano20k: femto-riscv-18-test-tangnano20k.fs
	$(call hil_femto,tangnano20k,0200)

.PHONY: hil-tangnano20k
hil-tangnano20k: $(HIL_BATCHES_tangnano20k:%=hil-%-tangnano20k) hil-femto-riscv-18-test-tangnano20k

# --- primer25k (GW5A-25A) ---
hil-%-primer25k: hil-%-primer25k.fs
	$(call hil_check,$*,primer25k,7c3e8265f4b7,tangprimer25k)

.PHONY: hil-primer25k
hil-primer25k: $(HIL_BATCHES_primer25k:%=hil-%-primer25k)

.PHONY: hil-all
hil-all: hil-tangnano9k hil-tangnano20k

# Run the known-broken tests of a board one by one. A pass means the bug is
# fixed: move the test back into a batch. Never fails, so the reference stays
# what a correct toolchain gives.
hil-%-broken:
	@for t in $(HIL_BROKEN_$*); do \
		if $(MAKE) --no-print-directory hil-$$t-$*; then echo "XPASS: $$t ($*)"; \
		else echo "XFAIL: $$t ($*)"; fi; \
	done

# ============================================================
# Tangnano20k
%-tangnano20k.fs: %-tangnano20k.json
	gowin_pack -c -d GW2A-18C -o $@ $<

%-tangnano20k.json: %-tangnano20k-synth.json tangnano20k.cst
	$(NEXTPNR) ${NEXTPNR_FLAGS} --json $< --write $@ --device GW2AR-LV18QN88C8/I7 --vopt family=GW2A-18C --vopt cst=tangnano20k.cst

%-tangnano20k-synth.json: %.v
	$(YOSYS) -D LEDS_NR=6 -D OSC_TYPE_OSC -D INV_BTN=1 -D CPU_FREQ=27 -D BAUD_RATE=115200 -D NUM_HCLK=5 -D RISCV_MEM_88K -p "read_verilog $^; synth_gowin -json $@ -family gw2a ${YOSYS_FLAGS}"

pll-nanolcd-tangnano20k-synth.json: pll/GW2A-18-dyn.vh pll-nanolcd/TOP.v pll-nanolcd/VGAMod.v
	$(YOSYS) -D INV_BTN=1 -p "read_verilog $^; synth_gowin -json $@ -family gw2a ${YOSYS_FLAGS}"

attosoc-tangnano20k-synth.json: attosoc/attosoc.v attosoc/picorv32.v
	$(YOSYS) -D INV_BTN=1 -p "read_verilog $^; synth_gowin -json $@ -family gw2a ${YOSYS_FLAGS}"

dvi-example-tangnano20k-synth.json: DVI/dvi-example.v DVI/dvi_sync.v DVI/dvi_top.v DVI/pll480.v DVI/tmds_encoder.v
	$(YOSYS) -D INV_BTN=1 -D IS_ELVDS=0 -p "read_verilog -I DVI $(filter %.v,$^); synth_gowin -json $@ -family gw2a ${YOSYS_FLAGS}"

# ============================================================
# TangPrimer20k
%-primer20k.fs: %-primer20k.json
	gowin_pack -c -d GW2A-18 -o $@ $<

%-primer20k.json: %-primer20k-synth.json primer20k.cst
	$(NEXTPNR) ${NEXTPNR_FLAGS} --json $< --write $@ --device GW2A-LV18PG256C8/I7 --vopt family=GW2A-18 --vopt cst=primer20k.cst

%-primer20k-synth.json: %.v
	$(YOSYS) -D LEDS_NR=6 -D OSC_TYPE_OSC -D INV_BTN=0 -D CPU_FREQ=27 -D BAUD_RATE=115200 -D NUM_HCLK=5 -p "read_verilog $^; synth_gowin -json $@ -family gw2a ${YOSYS_FLAGS}"

pll-nanolcd-primer20k-synth.json: pll/GW2A-18-dyn.vh pll-nanolcd/TOP.v pll-nanolcd/VGAMod.v
	$(YOSYS) -D INV_BTN=0 -p "read_verilog $^; synth_gowin -json $@ -family gw2a ${YOSYS_FLAGS}"

attosoc-%-synth.json: attosoc/attosoc.v attosoc/picorv32.v
	$(YOSYS) -D INV_BTN=0 -p "read_verilog $^; synth_gowin -json $@ -family gw2a ${YOSYS_FLAGS}"

dvi-example-primer20k-synth.json: DVI/dvi-example.v DVI/dvi_sync.v DVI/dvi_top.v DVI/pll480.v DVI/tmds_encoder.v
	$(YOSYS) -D INV_BTN=0 -D IS_ELVDS=0 -p "read_verilog -I DVI $(filter %.v,$^); synth_gowin -json $@ -family gw2a ${YOSYS_FLAGS}"

# ============================================================
# Tangnano (GW1N-1)
%-tangnano.fs: %-tangnano.json
	gowin_pack -c -d GW1N-1 -o $@ $^

%-tangnano.json: %-tangnano-synth.json tangnano.cst
	$(NEXTPNR) ${NEXTPNR_FLAGS} --json $< --write $@ --device GW1N-LV1QN48C6/I5 --vopt cst=tangnano.cst

%-tangnano-synth.json: %.v
	$(YOSYS) -D LEDS_NR=3 -D OSC_TYPE_OSCH -D INV_BTN=0 -D CPU_FREQ=24 -D NUM_HCLK=2 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

# HIL tests, built for coverage only: no reporter (HIL_SMALL in hil.v), TXD on an LED
hil-%-tangnano-synth.json: hil-%.v
	$(YOSYS) -D LEDS_NR=3 -D OSC_TYPE_OSCH -D INV_BTN=0 -D CPU_FREQ=24 -D NUM_HCLK=2 -D HIL_SMALL -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

pll-nanolcd-tangnano-synth.json: pll/GW1N-1-dyn.vh pll-nanolcd/TOP.v pll-nanolcd/VGAMod.v
	$(YOSYS) -D INV_BTN=0 -p "read_verilog $^; synth_gowin -noalu -json $@ ${YOSYS_FLAGS}"

# ============================================================
# Tangnano1k (GW1NZ-1)
%-tangnano1k.fs: %-tangnano1k.json
	gowin_pack -c -d GW1NZ-1 -o $@ $^

%-tangnano1k.json: %-tangnano1k-synth.json tangnano1k.cst
	$(NEXTPNR) ${NEXTPNR_FLAGS} --json $< --write $@ --device GW1NZ-LV1QN48C6/I5 --vopt cst=tangnano1k.cst

%-tangnano1k-synth.json: %.v
	$(YOSYS) -D LEDS_NR=3 -D OSC_TYPE_OSCZ -D INV_BTN=0 -D CPU_FREQ=27 -D NUM_HCLK=4 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

# HIL tests, built for coverage only: no reporter (HIL_SMALL in hil.v), TXD on an LED
hil-%-tangnano1k-synth.json: hil-%.v
	$(YOSYS) -D LEDS_NR=3 -D OSC_TYPE_OSCZ -D INV_BTN=0 -D CPU_FREQ=27 -D NUM_HCLK=4 -D HIL_SMALL -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

pll-nanolcd-tangnano1k.fs: pll-nanolcd-tangnano1k.json
	gowin_pack -c -d GW1NZ-1 --sspi_as_gpio --mspi_as_gpio -o $@ $^

pll-nanolcd-tangnano1k-synth.json: pll/GW1NZ-1-dyn.vh pll-nanolcd/TOP.v pll-nanolcd/VGAMod.v
	$(YOSYS) -D INV_BTN=0 -p "read_verilog $^; synth_gowin -noalu -json $@ ${YOSYS_FLAGS}"

# ============================================================
# Tangnano4k (GW1NS-4)
%-tangnano4k.fs: %-tangnano4k.json
	gowin_pack -c -d GW1NS-4 --mspi_as_gpio -o $@ $^

# XXX fix compression with emcu
emcu-%-tangnano4k.fs: emcu-%-tangnano4k.json
	gowin_pack -d GW1NS-4 --mspi_as_gpio -o $@ $^

%-tangnano4k.json: %-tangnano4k-synth.json tangnano4k.cst
	$(NEXTPNR) ${NEXTPNR_FLAGS} --json $< --write $@ --device GW1NSR-LV4CQN48PC7/I6 --vopt cst=tangnano4k.cst

%-tangnano4k-synth.json: %.v
	$(YOSYS) -D LEDS_NR=6 -D OSC_TYPE_OSCZ -D INV_BTN=0 -D FORCE_BRAM -D CPU_FREQ=27 -D BAUD_RATE=115200 -D NUM_HCLK=2 -D RISCV_MEM_16K -p "read_verilog $^; synth_gowin -nolutram -nowidelut -json $@ ${YOSYS_FLAGS}"

# ============================================================
# Tangnano9k (GW1N-9C)
%-tangnano9k.fs: %-tangnano9k.json
	gowin_pack -c -d GW1N-9C -o $@ $^

%-tangnano9k.json: %-tangnano9k-synth.json tangnano9k.cst
	$(NEXTPNR) ${NEXTPNR_FLAGS} --json $< --write $@ --device GW1NR-LV9QN88PC6/I5 --vopt family=GW1N-9C --vopt cst=tangnano9k.cst

%-tangnano9k-synth.json: %.v
	$(YOSYS) -D LEDS_NR=6 -D OSC_TYPE_OSC -D INV_BTN=0 -D CPU_FREQ=27 -D BAUD_RATE=115200 -D NUM_HCLK=5 -D HAS_FLASH608K -D RISCV_MEM_48K -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

pll-nanolcd-tangnano9k-synth.json: pll/GW1N-9C-dyn.vh pll-nanolcd/TOP.v pll-nanolcd/VGAMod.v
	$(YOSYS) -D INV_BTN=0 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

pll-nanolcd-tangnano9k.fs: pll-nanolcd-tangnano9k.json
	gowin_pack -c -d GW1N-9C --sspi_as_gpio --mspi_as_gpio -o $@ $^

dvi-example-tangnano9k-synth.json: DVI/dvi-example.v DVI/dvi_sync.v DVI/dvi_top.v DVI/pll480.v DVI/tmds_encoder.v
	$(YOSYS) -D INV_BTN=0 -D IS_ELVDS=1 -p "read_verilog -I DVI $(filter %.v,$^); synth_gowin -json $@ ${YOSYS_FLAGS}"

# ============================================================
# szfpga miniboard (GW1N-9)
%-miniszfpga.fs: %-miniszfpga.json
	gowin_pack -c -d GW1N-9 -o $@ $<

%-miniszfpga.json: %-miniszfpga-synth.json miniszfpga.cst
	$(NEXTPNR) ${NEXTPNR_FLAGS} --json $< --write $@ --device GW1N-LV9QN48C6/I5 --vopt family=GW1N-9 --vopt cst=miniszfpga.cst

%-miniszfpga-synth.json: %.v
	$(YOSYS) -D LEDS_NR=4 -D OSC_TYPE_OSC -D INV_BTN=0 -D CPU_FREQ=50 -D BAUD_RATE=115200 -D NUM_HCLK=5 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

# ============================================================
# szfpga (GW1N-9)
%-szfpga.fs: %-szfpga.json
	gowin_pack -c -d GW1N-9 -o $@ $<

%-szfpga.json: %-szfpga-synth.json szfpga.cst
	$(NEXTPNR) ${NEXTPNR_FLAGS} --seed=3 --json $< --write $@ --device GW1NR-LV9LQ144PC6/I5 --vopt family=GW1N-9 --vopt cst=szfpga.cst

%-szfpga-synth.json: %.v
	$(YOSYS) -D LEDS_NR=4 -D OSC_TYPE_OSC -D INV_BTN=0 -D CPU_FREQ=50 -D BAUD_RATE=115200 -D NUM_HCLK=5 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

# ============================================================
# tec0117 (GW1N-9)
%-tec0117.fs: %-tec0117.json
	gowin_pack -c -d GW1N-9 -o $@ $<

%-tec0117.json: %-tec0117-synth.json tec0117.cst
	$(NEXTPNR) ${NEXTPNR_FLAGS} --json $< --write $@ --device GW1NR-LV9QN88C6/I5 --vopt family=GW1N-9 --vopt cst=tec0117.cst

%-tec0117-synth.json: %.v
	$(YOSYS) -D LEDS_NR=8 -D OSC_TYPE_OSC -D INV_BTN=0 -D CPU_FREQ=12 -D BAUD_RATE=115200 -D NUM_HCLK=5 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

# ============================================================
# runber (GW1N-4)
%-runber.fs: %-runber.json
	gowin_pack -c -d GW1N-4 -o $@ $<

%-runber.json: %-runber-synth.json runber.cst
	$(NEXTPNR) ${NEXTPNR_FLAGS} --json $< --write $@ --device GW1N-UV4LQ144C6/I5 --vopt cst=runber.cst

%-runber-synth.json: %.v
	$(YOSYS) -D LEDS_NR=8 -D OSC_TYPE_OSC -D OSC_MHZ=210 -D INV_BTN=0 -D FORCE_BRAM -D CPU_FREQ=12 -D BAUD_RATE=115200 -D NUM_HCLK=5 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

# ============================================================
# GW5A boards: only the HIL tests are built here, the other GW5A examples
# are in gw5a/. The boards run at 50 MHz. NUM_HCLK only sizes hil/clkdiv.v,
# which is not built for GW5A.
GW5A_YOSYS_DEFS = -D OSC_TYPE_OSCA -D CPU_FREQ=50 -D BAUD_RATE=115200 -D FAMILY_GW5A -D NUM_HCLK=4

# The HIL bitstreams of a GW5A board, for gw5a/Makefile
.PHONY: primer25k-hil tangconsole60k-hil tangmega138k-hil tangconsole138k-hil
primer25k-hil: $(HIL_BATCHES_primer25k:%=hil-%-primer25k.fs)
tangconsole60k-hil: $(HIL_BATCHES_tangconsole60k:%=hil-%-tangconsole60k.fs)
tangmega138k-hil: $(HIL_BATCHES_tangmega138k:%=hil-%-tangmega138k.fs)
tangconsole138k-hil: $(HIL_BATCHES_tangconsole138k:%=hil-%-tangconsole138k.fs)

# Tang Primer 25K (GW5A-25A)
%-primer25k.fs: %-primer25k.json
	gowin_pack --sspi_as_gpio --cpu_as_gpio -d GW5A-25A -o $@ $<

%-primer25k.json: %-primer25k-synth.json gw5a/primer25k.cst
	$(NEXTPNR) ${NEXTPNR_FLAGS} --json $< --write $@ --device GW5A-LV25MG121NES --vopt cst=gw5a/primer25k.cst --vopt sspi_as_gpio

%-primer25k-synth.json: %.v
	$(YOSYS) $(GW5A_YOSYS_DEFS) -p "read_verilog $^; synth_gowin -json $@ -family gw5a -nolutram ${YOSYS_FLAGS}"

# Tang Console 60K (GW5AT-60B)
%-tangconsole60k.fs: %-tangconsole60k.json
	gowin_pack --cpu_as_gpio -d GW5AT-60B -o $@ $<

%-tangconsole60k.json: %-tangconsole60k-synth.json gw5a/tangconsole60k.cst
	$(NEXTPNR) ${NEXTPNR_FLAGS} --json $< --write $@ --device GW5AT-LV60PG484AC1/I0 --vopt cst=gw5a/tangconsole60k.cst

%-tangconsole60k-synth.json: %.v
	$(YOSYS) $(GW5A_YOSYS_DEFS) -p "read_verilog $^; synth_gowin -json $@ -family gw5a -nolutram ${YOSYS_FLAGS}"

# Tang Mega 138K and Tang Console 138K (GW5AST-138C)
%-tangmega138k.fs: %-tangmega138k.json
	gowin_pack --cpu_as_gpio -d GW5AST-138C -o $@ $<

%-tangmega138k.json: %-tangmega138k-synth.json gw5a/tangmega138k.cst
	$(NEXTPNR) ${NEXTPNR_FLAGS} --json $< --write $@ --device GW5AST-LV138PG484AC1/I0 --vopt cst=gw5a/tangmega138k.cst

%-tangmega138k-synth.json: %.v
	$(YOSYS) $(GW5A_YOSYS_DEFS) -p "read_verilog $^; synth_gowin -json $@ -family gw5a -nolutram ${YOSYS_FLAGS}"

%-tangconsole138k.fs: %-tangconsole138k.json
	gowin_pack --cpu_as_gpio -d GW5AST-138C -o $@ $<

%-tangconsole138k.json: %-tangconsole138k-synth.json gw5a/tangconsole138k.cst
	$(NEXTPNR) ${NEXTPNR_FLAGS} --json $< --write $@ --device GW5AST-LV138PG484AC1/I0 --vopt cst=gw5a/tangconsole138k.cst

%-tangconsole138k-synth.json: %.v
	$(YOSYS) $(GW5A_YOSYS_DEFS) -p "read_verilog $^; synth_gowin -json $@ -family gw5a -nolutram ${YOSYS_FLAGS}"

# ============================================================
#  Unpack
%-tangnano-unpacked.v: %-tangnano.fs
	gowin_unpack -d GW1N-1 -o $@ $^

%-tangnano1k-unpacked.v: %-tangnano1k.fs
	gowin_unpack -d GW1NZ-1 -o $@ $^

%-tangnano4k-unpacked.v: %-tangnano4k.fs
	gowin_unpack -d GW1NS-4 -o $@ $^

%-tangnano9k-unpacked.v: %-tangnano9k.fs
	gowin_unpack -d GW1N-9C -o $@ $^

%-tangnano20k-unpacked.v: %-tangnano20k.fs
	gowin_unpack -d GW2A-18C -o $@ $^

%-runber-unpacked.v: %-runber.fs
	gowin_unpack -d GW1N-4 -o $@ $^

%-tec0117-unpacked.v: %-tec0117.fs
	gowin_unpack -d GW1N-9 -o $@ $^

%-szfpga-unpacked.v: %-szfpga.fs
	gowin_unpack -d GW1N-9 -o $@ $^

%-primer20k-unpacked.v: %-primer20k.fs
	gowin_unpack -d GW2A-18 -o $@ $^

# hil-<test>-<board>-unpacked.v also matches the hil-%.v wrapper rule, and make
# takes that one because its prerequisites exist. Explicit rules win.
HIL_NAMES := $(sort $(shell sed -n 's/^.ifdef HIL_\([a-z][a-z0-9_]*\)$$/\1/p' hil.v | tr _ -) \
	$(HIL_BATCHES_tangnano9k) $(HIL_BATCHES_tangnano20k))
# $(call hil_unpack,BOARD,DEVICE)
define hil_unpack
$(HIL_NAMES:%=hil-%-$(1)-unpacked.v): hil-%-$(1)-unpacked.v: hil-%-$(1).fs
	gowin_unpack -d $(2) -o $$@ $$^
endef
$(eval $(call hil_unpack,tangnano,GW1N-1))
$(eval $(call hil_unpack,tangnano1k,GW1NZ-1))
$(eval $(call hil_unpack,tangnano4k,GW1NS-4))
$(eval $(call hil_unpack,tangnano9k,GW1N-9C))
$(eval $(call hil_unpack,tangnano20k,GW2A-18C))
$(eval $(call hil_unpack,runber,GW1N-4))
$(eval $(call hil_unpack,tec0117,GW1N-9))
$(eval $(call hil_unpack,szfpga,GW1N-9))
$(eval $(call hil_unpack,primer20k,GW2A-18))

# ============================================================
# Multiboot
.PHONY: tangnano20k-multiboot

tangnano20k-multiboot: \
	blinky-tangnano20k.json \
	shift-tangnano20k.json
	gowin_pack -c -d GW2A-18C \
	  	--multiboot_address 0x200000 \
		-o blinky-tangnano20k-multiboot.fs \
		blinky-tangnano20k.json

	gowin_pack -c -d GW2A-18C \
	  	--multiboot_address 0x000000 \
		-o shift-tangnano20k-multiboot.fs \
		shift-tangnano20k.json

	openFPGALoader -b tangnano20k -f \
		blinky-tangnano20k-multiboot.fs

	openFPGALoader -b tangnano20k -f \
		--offset 0x200000 \
		shift-tangnano20k-multiboot.fs

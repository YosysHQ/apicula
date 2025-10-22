YOSYS ?= yosys
NEXTPNR ?= nextpnr-himbaechel
YOSYS_FLAGS = -setundef

.DEFAULT_GOAL := all

all: \
	blinky-tangnano20k.fs shift-tangnano20k.fs blinky-tbuf-tangnano20k.fs blinky-oddr-tangnano20k.fs \
	blinky-osc-tangnano20k.fs tlvds-tangnano20k.fs elvds-tangnano20k.fs oddr-tlvds-tangnano20k.fs \
	blinky-clkdiv-tangnano20k.fs dvi-example-tangnano20k.fs blinky-clkdiv-dhcen-tangnano20k.fs \
	oddr-elvds-tangnano20k.fs pll-nanolcd-tangnano20k.fs attosoc-tangnano20k.fs \
	oser4-tangnano20k.fs ovideo-tangnano20k.fs oser8-tangnano20k.fs oser10-tangnano20k.fs \
	iddr-tangnano20k.fs iddrc-tangnano20k.fs iodelay-tangnano20k.fs \
	ides4-tangnano20k.fs ivideo-tangnano20k.fs ides8-tangnano20k.fs ides10-tangnano20k.fs \
	bsram-pROM-tangnano20k.fs bsram-SDPB-tangnano20k.fs bsram-SP-tangnano20k.fs \
	bsram-DPB-tangnano20k.fs bsram-pROMX9-tangnano20k.fs bsram-SDPX9B-tangnano20k.fs \
	bsram-SPX9-tangnano20k.fs bsram-DPX9B-tangnano20k.fs  femto-riscv-memtest-tangnano20k.fs \
	femto-riscv-15-tangnano20k.fs femto-riscv-16-tangnano20k.fs femto-riscv-18-tangnano20k.fs \
	dsp-mult18x18-tangnano20k.fs dsp-mult36x36-tangnano20k.fs dsp-padd9-tangnano20k.fs dsp-padd18-tangnano20k.fs \
	dsp-mult9x9-tangnano20k.fs dsp-alu54d-tangnano20k.fs dsp-multalu18x18-tangnano20k.fs \
	dsp-multalu36x18-tangnano20k.fs dsp-multaddalu18x18-tangnano20k.fs \
	dqce-tangnano20k.fs  dcs-tangnano20k.fs \
	\
	blinky-primer20k.fs shift-primer20k.fs blinky-tbuf-primer20k.fs blinky-oddr-primer20k.fs \
	blinky-osc-primer20k.fs tlvds-primer20k.fs elvds-primer20k.fs oddr-tlvds-primer20k.fs \
	blinky-clkdiv-primer20k.fs dvi-example-primer20k.fs blinky-clkdiv-dhcen-primer20k.fs \
	oddr-elvds-primer20k.fs pll-nanolcd-primer20k.fs attosoc-primer20k.fs \
	oser4-primer20k.fs ovideo-primer20k.fs oser8-primer20k.fs oser10-primer20k.fs \
	iddr-primer20k.fs iddrc-primer20k.fs iodelay-primer20k.fs \
	ides4-primer20k.fs ivideo-primer20k.fs ides8-primer20k.fs ides10-primer20k.fs \
	bsram-pROM-primer20k.fs bsram-SDPB-primer20k.fs bsram-SP-primer20k.fs \
	bsram-DPB-primer20k.fs bsram-pROMX9-primer20k.fs bsram-SDPX9B-primer20k.fs \
	bsram-SPX9-primer20k.fs bsram-DPX9B-primer20k.fs \
	femto-riscv-15-primer20k.fs femto-riscv-16-primer20k.fs femto-riscv-18-primer20k.fs \
	dsp-mult18x18-primer20k.fs dsp-mult36x36-primer20k.fs dsp-padd9-primer20k.fs dsp-padd18-primer20k.fs \
	dsp-mult9x9-primer20k.fs dsp-alu54d-primer20k.fs dsp-multalu18x18-primer20k.fs \
	dsp-multalu36x18-primer20k.fs dsp-multaddalu18x18-primer20k.fs \
	dqce-primer20k.fs  dcs-primer20k.fs \
	\
	blinky-tangnano.fs shift-tangnano.fs blinky-tbuf-tangnano.fs blinky-oddr-tangnano.fs \
	blinky-osc-tangnano.fs elvds-tangnano.fs oddr-elvds-tangnano.fs pll-nanolcd-tangnano.fs \
	blinky-clkdiv-tangnano.fs blinky-clkdiv-dhcen-tangnano.fs \
	oser4-tangnano.fs ovideo-tangnano.fs oser8-tangnano.fs oser10-tangnano.fs \
	iddr-tangnano.fs iddrc-tangnano.fs iodelay-tangnano.fs \
	ides4-tangnano.fs ivideo-tangnano.fs ides8-tangnano.fs ides10-tangnano.fs \
	bsram-pROM-tangnano.fs bsram-SDPB-tangnano.fs bsram-DPB-tangnano.fs \
	bsram-SP-tangnano.fs bsram-pROMX9-tangnano.fs bsram-SDPX9B-tangnano.fs \
	bsram-SPX9-tangnano.fs bsram-DPX9B-tangnano.fs \
	\
	blinky-tangnano1k.fs shift-tangnano1k.fs blinky-tbuf-tangnano1k.fs blinky-oddr-tangnano1k.fs \
	blinky-osc-tangnano1k.fs elvds-tangnano1k.fs oddr-elvds-tangnano1k.fs pll-nanolcd-tangnano1k.fs \
	blinky-clkdiv-tangnano1k.fs blinky-clkdiv-dhcen-tangnano1k.fs \
	oser4-tangnano1k.fs ovideo-tangnano1k.fs oser8-tangnano1k.fs oser10-tangnano1k.fs \
	iddr-tangnano1k.fs iddrc-tangnano1k.fs iodelay-tangnano1k.fs \
	ides4-tangnano1k.fs ivideo-tangnano1k.fs ides8-tangnano1k.fs ides10-tangnano1k.fs \
	bsram-pROM-tangnano1k.fs bsram-SDPB-tangnano1k.fs bsram-DPB16-tangnano1k.fs \
	bsram-SP-tangnano1k.fs bsram-pROMX9-tangnano1k.fs bsram-SDPX9B-tangnano1k.fs \
	bsram-SPX9-tangnano1k.fs bsram-DPX9B18-tangnano1k.fs \
	dqce-tangnano1k.fs dcs-tangnano1k.fs userflash-tangnano1k.fs bandgap-tangnano1k.fs \
	\
	blinky-tangnano4k.fs shift-tangnano4k.fs blinky-tbuf-tangnano4k.fs blinky-oddr-tangnano4k.fs \
	blinky-osc-tangnano4k.fs tlvds-tangnano4k.fs elvds-tangnano4k.fs oddr-tlvds-tangnano4k.fs \
	blinky-clkdiv-tangnano4k.fs blinky-clkdiv-dhcen-tangnano4k.fs \
	oddr-elvds-tangnano4k.fs blinky-pll-tangnano4k.fs oser16-tangnano4k.fs \
	oser4-tangnano4k.fs ovideo-tangnano4k.fs oser8-tangnano4k.fs oser10-tangnano4k.fs \
	iddr-tangnano4k.fs iddrc-tangnano4k.fs ides16-tangnano4k.fs \
	ides4-tangnano4k.fs ivideo-tangnano4k.fs ides8-tangnano4k.fs ides10-tangnano4k.fs \
	oser10-tlvds-tangnano4k.fs iodelay-tangnano4k.fs mipi-out-tangnano4k.fs  femto-riscv-memtest-tangnano4k.fs \
	femto-riscv-15-tangnano4k.fs femto-riscv-16-tangnano4k.fs femto-riscv-18-tangnano4k.fs \
	dsp-mult18x18-tangnano4k.fs dsp-mult36x36-tangnano4k.fs dsp-padd9-tangnano4k.fs dsp-padd18-tangnano4k.fs \
	dsp-mult9x9-tangnano4k.fs dsp-alu54d-tangnano4k.fs dsp-multalu18x18-tangnano4k.fs \
	dsp-multalu36x18-tangnano4k.fs dsp-multaddalu18x18-tangnano4k.fs \
	dqce-tangnano4k.fs dcs-tangnano4k.fs emcu-blinky-tangnano4k.fs emcu-with-apb-blinky-tangnano4k.fs \
	emcu-with-apb-spi-tangnano4k.fs i3c-tangnano4k.fs mipi-out-tangnano4k.fs \
	\
	blinky-tangnano9k.fs shift-tangnano9k.fs blinky-tbuf-tangnano9k.fs blinky-oddr-tangnano9k.fs \
	blinky-clkdiv-tangnano9k.fs dvi-example-tangnano9k.fs\
	blinky-osc-tangnano9k.fs tlvds-tangnano9k.fs elvds-tangnano9k.fs oddr-tlvds-tangnano9k.fs \
	oddr-elvds-tangnano9k.fs pll-nanolcd-tangnano9k.fs oser16-tangnano9k.fs attosoc-tangnano9k.fs \
	oser4-tangnano9k.fs ovideo-tangnano9k.fs oser8-tangnano9k.fs oser10-tangnano9k.fs \
	iddr-tangnano9k.fs iddrc-tangnano9k.fs iodelay-tangnano9k.fs mipi-out-tangnano4k.fs \
	ides4-tangnano9k.fs ivideo-tangnano9k.fs ides8-tangnano9k.fs ides10-tangnano9k.fs \
	bsram-pROM-tangnano9k.fs bsram-SDPB-tangnano9k.fs bsram-SP-tangnano9k.fs \
	bsram-DPB-tangnano9k.fs bsram-pROMX9-tangnano9k.fs bsram-SDPX9B-tangnano9k.fs \
	bsram-SPX9-tangnano9k.fs bsram-DPX9B-tangnano9k.fs bsram-DPX9B18-tangnano9k.fs \
	oser10-elvds-tangnano9k.fs femto-riscv-memtest-tangnano9k.fs \
	femto-riscv-15-tangnano9k.fs femto-riscv-16-tangnano9k.fs femto-riscv-18-tangnano9k.fs \
	dsp-mult18x18-tangnano9k.fs dsp-mult36x36-tangnano9k.fs dsp-padd9-tangnano9k.fs dsp-padd18-tangnano9k.fs \
	dsp-mult9x9-tangnano9k.fs dsp-alu54d-tangnano9k.fs dsp-multalu18x18-tangnano9k.fs \
	dsp-multalu36x18-tangnano9k.fs dsp-multaddalu18x18-tangnano9k.fs \
	dqce-tangnano9k.fs dcs-tangnano9k.fs femto-riscv-userflash-tangnano9k.fs \
	i3c-tangnano9k.fs mipi-tangnano9k.fs mipi-out-tangnano9k.fs \
	\
	blinky-szfpga.fs shift-szfpga.fs blinky-tbuf-szfpga.fs blinky-oddr-szfpga.fs \
	blinky-osc-szfpga.fs tlvds-szfpga.fs elvds-szfpga.fs oddr-tlvds-szfpga.fs \
	blinky-clkdiv-szfpga.fs blinky-clkdiv-dhcen-szfpga.fs \
	oddr-elvds-szfpga.fs blinky-pll-szfpga.fs oser16-szfpga.fs attosoc-szfpga.fs \
	oser4-szfpga.fs ovideo-szfpga.fs oser8-szfpga.fs oser10-szfpga.fs \
	iddr-szfpga.fs iddrc-szfpga.fs ides16-szfpga.fs iodelay-szfpga.fs \
	ides4-szfpga.fs ivideo-szfpga.fs ides8-szfpga.fs ides10-szfpga.fs \
	bsram-pROM-szfpga.fs bsram-SDPB-szfpga.fs bsram-SP-szfpga.fs \
	bsram-pROMX9-szfpga.fs bsram-SDPX9B-szfpga.fs \
	bsram-SPX9-szfpga.fs \
	femto-riscv-15-szfpga.fs femto-riscv-16-szfpga.fs femto-riscv-18-szfpga.fs \
	dsp-mult18x18-szfpga.fs dsp-mult36x36-szfpga.fs dsp-padd9-szfpga.fs dsp-padd18-szfpga.fs \
	dsp-mult9x9-szfpga.fs dsp-alu54d-szfpga.fs dsp-multalu18x18-szfpga.fs \
	dsp-multalu36x18-szfpga.fs dsp-multaddalu18x18-szfpga.fs \
	\
	blinky-tec0117.fs shift-tec0117.fs blinky-tbuf-tec0117.fs blinky-oddr-tec0117.fs \
	blinky-osc-tec0117.fs tlvds-tec0117.fs elvds-tec0117.fs oddr-tlvds-tec0117.fs \
	blinky-clkdiv-tec0117.fs blinky-clkdiv-dhcen-tec0117.fs \
	oddr-elvds-tec0117.fs blinky-pll-tec0117.fs oser16-tec0117.fs attosoc-tec0117.fs \
	oser4-tec0117.fs ovideo-tec0117.fs oser8-tec0117.fs oser10-tec0117.fs \
	iddr-tec0117.fs iddrc-tec0117.fs ides16-tec0117.fs iodelay-tec0117.fs \
	ides4-tec0117.fs ivideo-tec0117.fs ides8-tec0117.fs ides10-tec0117.fs \
	dsp-mult18x18-tec0117.fs dsp-mult36x36-tec0117.fs dsp-padd9-tec0117.fs dsp-padd18-tec0117.fs \
	dsp-mult9x9-tec0117.fs dsp-alu54d-tec0117.fs dsp-multalu18x18-tec0117.fs \
	dsp-multalu36x18-tec0117.fs dsp-multaddalu18x18-tec0117.fs \
	\
	blinky-runber.fs shift-runber.fs blinky-tbuf-runber.fs blinky-oddr-runber.fs \
	blinky-osc-runber.fs tlvds-runber.fs elvds-runber.fs oddr-tlvds-runber.fs \
	blinky-clkdiv-runber.fs \
	oddr-elvds-runber.fs blinky-pll-runber.fs \
	oser4-runber.fs ovideo-runber.fs oser8-runber.fs oser10-runber.fs \
	iddr-runber.fs iddrc-runber.fs iodelay-runber.fs \
	ides4-runber.fs ivideo-runber.fs ides8-runber.fs ides10-runber.fs \
	dsp-mult36x36-runber.fs dsp-padd9-runber.fs dsp-padd18-runber.fs \
	dsp-mult9x9-runber.fs dsp-alu54d-runber.fs dsp-multalu18x18-runber.fs \
	dsp-multalu36x18-runber.fs dsp-multaddalu18x18-runber.fs

unpacked:\
	blinky-tangnano20k-unpacked.v shift-tangnano20k-unpacked.v \
	blinky-tbuf-tangnano20k-unpacked.v blinky-oddr-tangnano20k-unpacked.v \
	blinky-osc-tangnano20k-unpacked.v tlvds-tangnano20k-unpacked.v \
	elvds-tangnano20k-unpacked.v oddr-tlvds-tangnano20k-unpacked.v \
	oddr-elvds-tangnano20k-unpacked.v pll-nanolcd-tangnano20k-unpacked.v \
	attosoc-tangnano20k-unpacked.v oser4-tangnano20k-unpacked.v ovideo-tangnano20k-unpacked.v \
	oser8-tangnano20k-unpacked.v oser10-tangnano20k-unpacked.v \
	ides4-tangnano20k-unpacked.v ivideo-tangnano20k-unpacked.v ides8-tangnano20k-unpacked.v \
	ides10-tangnano20k-unpacked.v \
	bsram-pROM-tangnano20k-unpacked.v bsram-SDPB-tangnano20k-unpacked.v bsram-SP-tangnano20k-unpacked.v \
	bsram-DPB-tangnano20k-unpacked.v bsram-pROMX9-tangnano20k-unpacked.v \
	bsram-SDPX9B-tangnano20k-unpacked.v bsram-SPX9-tangnano-unpacked.v \
	bsram-DPX9B-tangnano20k-unpacked.v \
	femto-riscv-15-tangnano20k-unpacked.v femto-riscv-16-tangnano20k-unpacked.v femto-riscv-18-tangnano20k-unpacked.v \
	\
	blinky-primer20k-unpacked.v shift-primer20k-unpacked.v blinky-tbuf-primer20k-unpacked.v \
	blinky-oddr-primer20k-unpacked.v blinky-osc-primer20k-unpacked.v tlvds-primer20k-unpacked.v \
	elvds-primer20k-unpacked.v oddr-tlvds-primer20k-unpacked.v \
	oddr-elvds-primer20k-unpacked.v pll-nanolcd-primer20k-unpacked.v attosoc-primer20k-unpacked.v \
	oser4-primer20k-unpacked.v ovideo-primer20k-unpacked.v oser8-primer20k-unpacked.v \
	oser10-primer20k-unpacked.v ides4-primer20k-unpacked.v ivideo-primer20k-unpacked.v \
	ides8-primer20k-unpacked.v ides10-primer20k-unpacked.v \
	bsram-pROM-primer20k-unpacked.v bsram-SDPB-primer20k-unpacked.v bsram-SP-primer20k-unpacked.v \
	bsram-DPB-primer20k-unpacked.v bsram-pROMX9-primer20k-unpacked.v \
	bsram-SDPX9B-primer20k-unpacked.v bsram-SPX9-tangnano-unpacked.v \
	bsram-DPX9B-primer20k-unpacked.v \
	femto-riscv-15-primer20k-unpacked.v femto-riscv-16-primer20k-unpacked.v femto-riscv-18-primer20k-unpacked.v \
	\
	blinky-tangnano-unpacked.v shift-tangnano-unpacked.v blinky-tbuf-tangnano-unpacked.v \
	blinky-oddr-tangnano-unpacked.v blinky-osc-tangnano-unpacked.v elvds-tangnano-unpacked.v \
	oddr-elvds-tangnano-unpacked.v pll-nanolcd-tangnano-unpacked.v \
	oser4-tangnano-unpacked.v ovideo-tangnano-unpacked.v oser8-tangnano-unpacked.v \
	oser10-tangnano-unpacked.v ides4-tangnano-unpacked.v ivideo-tangnano-unpacked.v \
	ides8-tangnano-unpacked.v ides10-tangnano-unpacked.v bsram-pROM-tangnano-unpacked.v \
	bsram-SDPB-tangnano-unpacked.v bsram-SP-tangnano-unpacked.v bsram-pROMX9-tangnano-unpacked.v \
	bsram-SDPX9B-tangnano-unpacked.v bsram-SPX9-tangnano-unpacked.v \
	bsram-DPB-tangnano-unpacked.v bsram-DPX9B-tangnano-unpacked.v \
	\
	blinky-tangnano1k-unpacked.v shift-tangnano1k-unpacked.v blinky-tbuf-tangnano1k-unpacked.v \
	blinky-oddr-tangnano1k-unpacked.v blinky-osc-tangnano1k-unpacked.v elvds-tangnano1k-unpacked.v \
	oddr-elvds-tangnano1k-unpacked.v pll-nanolcd-tangnano1k-unpacked.v oser4-tangnano1k-unpacked.v \
	ovideo-tangnano1k-unpacked.v oser8-tangnano1k-unpacked.v oser10-tangnano1k-unpacked.v \
	ides4-tangnano1k-unpacked.v ivideo-tangnano1k-unpacked.v ides8-tangnano1k-unpacked.v \
	ides10-tangnano1k-unpacked.v bsram-pROM-tangnano1k-unpacked.v bsram-SDPB-tangnano1k-unpacked.v \
	bsram-DPB16-tangnano1k-unpacked.v bsram-SP-tangnano1k-unpacked.v \
	bsram-pROMX9-tangnano1k-unpacked.v bsram-SDPX9B-tangnano1k-unpacked.v \
	bsram-SPX9-tangnano1k-unpacked.v bsram-DPX9B18-tangnano1k-unpacked.v \
	\
	blinky-tangnano4k-unpacked.v shift-tangnano4k-unpacked.v blinky-tbuf-tangnano4k-unpacked.v \
	blinky-oddr-tangnano4k-unpacked.v blinky-osc-tangnano4k-unpacked.v tlvds-tangnano4k-unpacked.v \
	elvds-tangnano4k-unpacked.v oddr-tlvds-tangnano4k-unpacked.v oddr-elvds-tangnano4k-unpacked.v \
	blinky-pll-tangnano4k-unpacked.v oser16-tangnano4k-unpacked.v oser4-tangnano4k-unpacked.v \
	ovideo-tangnano4k-unpacked.v oser8-tangnano4k-unpacked.v oser10-tangnano4k-unpacked.v \
	ides16-tangnano4k-unpacked.v ides4-tangnano4k-unpacked.v ivideo-tangnano4k-unpacked.v \
	ides8-tangnano4k-unpacked.v ides10-tangnano4k-unpacked.v oser10-tlvds-tangnano4k-unpacked.v \
	femto-riscv-15-tangnano4k-unpacked.v femto-riscv-16-tangnano4k-unpacked.v femto-riscv-18-tangnano4k-unpacked.v \
	\
	blinky-tangnano9k-unpacked.v shift-tangnano9k-unpacked.v blinky-tbuf-tangnano9k-unpacked.v \
	blinky-oddr-tangnano9k-unpacked.v blinky-osc-tangnano9k-unpacked.v tlvds-tangnano9k-unpacked.v \
	elvds-tangnano9k-unpacked.v oddr-tlvds-tangnano9k-unpacked.v oddr-elvds-tangnano9k-unpacked.v \
	pll-nanolcd-tangnano9k-unpacked.v oser16-tangnano9k-unpacked.v attosoc-tangnano9k-unpacked.v \
	oser4-tangnano9k-unpacked.v ovideo-tangnano9k-unpacked.v oser8-tangnano9k-unpacked.v \
	oser10-tangnano9k-unpacked.v ides4-tangnano9k-unpacked.v ivideo-tangnano9k-unpacked.v \
	ides8-tangnano9k-unpacked.v ides10-tangnano9k-unpacked.v \
	bsram-pROM-tangnano9k-unpacked.v bsram-SDPB-tangnano9k-unpacked.v bsram-SP-tangnano9k-unpacked.v \
	bsram-DPB-tangnano9k-unpacked.v bsram-pROMX9-tangnano9k-unpacked.v \
	bsram-SDPX9B-tangnano9k-unpacked.v bsram-SPX9-tangnano-unpacked.v \
	bsram-DPX9B-tangnano9k-unpacked.v \
	femto-riscv-15-tangnano9k-unpacked.v femto-riscv-16-tangnano9k-unpacked.v femto-riscv-18-tangnano9k-unpacked.v \
	\
	blinky-szfpga-unpacked.v shift-szfpga-unpacked.v blinky-tbuf-szfpga-unpacked.v \
	blinky-oddr-szfpga-unpacked.v blinky-osc-szfpga-unpacked.v tlvds-szfpga-unpacked.v \
	elvds-szfpga-unpacked.v oddr-tlvds-szfpga-unpacked.v oddr-elvds-szfpga-unpacked.v \
	blinky-pll-szfpga-unpacked.v oser16-szfpga-unpacked.v attosoc-szfpga-unpacked.v \
	oser4-szfpga-unpacked.v ovideo-szfpga-unpacked.v oser8-szfpga-unpacked.v \
	oser10-szfpga-unpacked.v ides16-szfpga-unpacked.v ides4-szfpga-unpacked.v \
	ivideo-szfpga-unpacked.v ides8-szfpga-unpacked.v ides10-szfpga-unpacked.v \
	bsram-pROM-szfpga-unpacked.v bsram-SDPB-szfpga-unpacked.v bsram-SP-szfpga-unpacked.v \
	bsram-SDPX9B-szfpga-unpacked.v bsram-SPX9-tangnano-unpacked.v \
	bsram-pROMX9-szfpga-unpacked.v \
	femto-riscv-15-szfpga-unpacked.v femto-riscv-16-szfpga-unpacked.v femto-riscv-18-szfpga-unpacked.v \
	\
	blinky-tec0117-unpacked.v shift-tec0117-unpacked.v blinky-tbuf-tec0117-unpacked.v \
	blinky-oddr-tec0117-unpacked.v blinky-osc-tec0117-unpacked.v tlvds-tec0117-unpacked.v \
	elvds-tec0117-unpacked.v oddr-tlvds-tec0117-unpacked.v oddr-elvds-tec0117-unpacked.v \
	blinky-pll-tec0117-unpacked.v oser16-tec0117-unpacked.v attosoc-tec0117-unpacked.v \
	oser4-tec0117-unpacked.v ovideo-tec0117-unpacked.v oser8-tec0117-unpacked.v \
	oser10-tec0117-unpacked.v ides16-tec0117-unpacked.v ides4-tec0117-unpacked.v \
	ivideo-tec0117-unpacked.v ides8-tec0117-unpacked.v ides10-tec0117-unpacked.v \
	femto-riscv-15-tangnano9k-unpacked.v femto-riscv-16-tangnano9k-unpacked.v femto-riscv-18-tangnano9k-unpacked.v \
	\
	blinky-runber-unpacked.v shift-runber-unpacked.v blinky-tbuf-runber-unpacked.v \
	blinky-oddr-runber-unpacked.v blinky-osc-runber-unpacked.v tlvds-runber-unpacked.v \
	elvds-runber-unpacked.v oddr-tlvds-runber-unpacked.v oddr-elvds-runber-unpacked.v \
	blinky-pll-runber-unpacked.v oser4-runber-unpacked.v ovideo-runber-unpacked.v \
	oser8-runber-unpacked.v oser10-runber-unpacked.v ides4-runber-unpacked.v \
	ivideo-runber-unpacked.v ides8-runber-unpacked.v ides10-runber-unpacked.v

clean: 
	rm -f *.json *.fs *-unpacked.v
	
.PHONY: unpacked clean

# ============================================================
# Tangnano20k
%-tangnano20k.fs: %-tangnano20k.json
	gowin_pack -c -d GW2A-18C -o $@ $<

%-tangnano20k.json: %-tangnano20k-synth.json tangnano20k.cst
	$(NEXTPNR) --json $< --write $@ --device GW2AR-LV18QN88C8/I7 --vopt family=GW2A-18C --vopt cst=tangnano20k.cst

%-tangnano20k-synth.json: %.v
	$(YOSYS) -D LEDS_NR=6 -D OSC_TYPE_OSC -D INV_BTN=1 -D CPU_FREQ=27 -D BAUD_RATE=115200 -D NUM_HCLK=5 -D RISCV_MEM_88K -p "read_verilog $^; synth_gowin -json $@ -family gw2a ${YOSYS_FLAGS}"

pll-nanolcd-tangnano20k-synth.json: pll/GW2A-18-dyn.vh pll-nanolcd/TOP.v pll-nanolcd/VGAMod.v
	$(YOSYS) -D INV_BTN=1 -p "read_verilog $^; synth_gowin -json $@ -family gw2a ${YOSYS_FLAGS}"

bsram-%-tangnano20k-synth.json: pll/GW2A-18-dyn.vh io565.vh display-480x272.v %-image-rom.v %-video-ram.v %.v clock-rPLL.v
	$(YOSYS) -D INV_BTN=1 -p "read_verilog $^; synth_gowin -json $@ -family gw2a ${YOSYS_FLAGS}"

attosoc-tangnano20k-synth.json: attosoc/attosoc.v attosoc/picorv32.v
	$(YOSYS) -D INV_BTN=1 -p "read_verilog $^; synth_gowin -json $@ -family gw2a ${YOSYS_FLAGS}"

dvi-example-tangnano20k-synth.json: DVI/dvi-example.v DVI/pll480.v DVI/tmds-channel.v
	$(YOSYS) -D INV_BTN=1 -D IS_ELVDS=0 -p "read_verilog -sv $^; synth_gowin -json $@ -family gw2a ${YOSYS_FLAGS}"

# ============================================================
# TangPrimer20k
%-primer20k.fs: %-primer20k.json
	gowin_pack -c -d GW2A-18 -o $@ $<

%-primer20k.json: %-primer20k-synth.json primer20k.cst
	$(NEXTPNR) --json $< --write $@ --device GW2A-LV18PG256C8/I7 --vopt family=GW2A-18 --vopt cst=primer20k.cst

%-primer20k-synth.json: %.v
	$(YOSYS) -D LEDS_NR=6 -D OSC_TYPE_OSC -D INV_BTN=0 -D CPU_FREQ=27 -D BAUD_RATE=115200 -D NUM_HCLK=5 -p "read_verilog $^; synth_gowin -json $@ -family gw2a ${YOSYS_FLAGS}"

pll-nanolcd-primer20k-synth.json: pll/GW2A-18-dyn.vh pll-nanolcd/TOP.v pll-nanolcd/VGAMod.v
	$(YOSYS) -D INV_BTN=0 -p "read_verilog $^; synth_gowin -json $@ -family gw2a ${YOSYS_FLAGS}"

bsram-%-primer20k-synth.json: pll/GW2A-18-dyn.vh io565.vh display-480x272.v %-image-rom.v %-video-ram.v %.v clock-rPLL.v
	$(YOSYS) -D INV_BTN=0 -p "read_verilog $^; synth_gowin -json $@ -family gw2a ${YOSYS_FLAGS}"

attosoc-%-synth.json: attosoc/attosoc.v attosoc/picorv32.v
	$(YOSYS) -D INV_BTN=0 -p "read_verilog $^; synth_gowin -json $@ -family gw2a ${YOSYS_FLAGS}"

dvi-example-primer20k-synth.json: DVI/dvi-example.v DVI/pll480.v DVI/tmds-channel.v
	$(YOSYS) -D INV_BTN=0 -D IS_ELVDS=0 -p "read_verilog -sv $^; synth_gowin -json $@ -family gw2a ${YOSYS_FLAGS}"

# ============================================================
# Tangnano (GW1N-1)
%-tangnano.fs: %-tangnano.json
	gowin_pack -c -d GW1N-1 -o $@ $^

%-tangnano.json: %-tangnano-synth.json tangnano.cst
	$(NEXTPNR) --json $< --write $@ --device GW1N-LV1QN48C6/I5 --vopt cst=tangnano.cst

%-tangnano-synth.json: %.v
	$(YOSYS) -D LEDS_NR=3 -D OSC_TYPE_OSCH -D INV_BTN=0 -D NUM_HCLK=2 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

pll-nanolcd-tangnano-synth.json: pll/GW1N-1-dyn.vh pll-nanolcd/TOP.v pll-nanolcd/VGAMod.v
	$(YOSYS) -D INV_BTN=0 -p "read_verilog $^; synth_gowin -noalu -json $@ ${YOSYS_FLAGS}"

bsram-%-tangnano-synth.json: pll/GW1N-1-dyn.vh io565.vh display-480x272.v %-image-rom.v %-video-ram.v %.v clock-rPLL.v
	$(YOSYS) -D INV_BTN=0 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

# ============================================================
# Tangnano1k (GW1NZ-1)
%-tangnano1k.fs: %-tangnano1k.json
	gowin_pack -c -d GW1NZ-1 -o $@ $^

%-tangnano1k.json: %-tangnano1k-synth.json tangnano1k.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NZ-LV1QN48C6/I5 --vopt cst=tangnano1k.cst

%-tangnano1k-synth.json: %.v
	$(YOSYS) -D LEDS_NR=3 -D OSC_TYPE_OSCZ -D INV_BTN=0 -D NUM_HCLK=4 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

pll-nanolcd-tangnano1k.fs: pll-nanolcd-tangnano1k.json
	gowin_pack -c -d GW1NZ-1 --sspi_as_gpio --mspi_as_gpio -o $@ $^

pll-nanolcd-tangnano1k-synth.json: pll/GW1NZ-1-dyn.vh pll-nanolcd/TOP.v pll-nanolcd/VGAMod.v
	$(YOSYS) -D INV_BTN=0 -p "read_verilog $^; synth_gowin -noalu -json $@ ${YOSYS_FLAGS}"
	
bsram-%-tangnano1k-synth.json: pll/GW1NZ-1-dyn.vh io565.vh display-480x272.v %-image-rom.v %-video-ram.v %.v clock-rPLL.v
	$(YOSYS) -D INV_BTN=0 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

# ============================================================
# Tangnano4k (GW1NS-4)
%-tangnano4k.fs: %-tangnano4k.json
	gowin_pack -c -d GW1NS-4 --mspi_as_gpio -o $@ $^

# XXX fix compression with emcu
emcu-%-tangnano4k.fs: emcu-%-tangnano4k.json
	gowin_pack -d GW1NS-4 --mspi_as_gpio -o $@ $^

%-tangnano4k.json: %-tangnano4k-synth.json tangnano4k.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NSR-LV4CQN48PC7/I6 --vopt cst=tangnano4k.cst

%-tangnano4k-synth.json: %.v
	$(YOSYS) -D LEDS_NR=6 -D OSC_TYPE_OSCZ -D INV_BTN=0 -D FORCE_BRAM -D CPU_FREQ=27 -D BAUD_RATE=115200 -D NUM_HCLK=2 -D RISCV_MEM_16K -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

%-pll-tangnano4k-synth.json: pll/GW1NS-4-dyn.vh %-pll-vr.v
	$(YOSYS) -D INV_BTN=0 -D LEDS_NR=6 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"
	

# ============================================================
# Tangnano9k (GW1N-9C)
%-tangnano9k.fs: %-tangnano9k.json
	gowin_pack -c -d GW1N-9C -o $@ $^

%-tangnano9k.json: %-tangnano9k-synth.json tangnano9k.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NR-LV9QN88PC6/I5 --vopt family=GW1N-9C --vopt cst=tangnano9k.cst

%-tangnano9k-synth.json: %.v
	$(YOSYS) -D LEDS_NR=6 -D OSC_TYPE_OSC -D INV_BTN=0 -D CPU_FREQ=27 -D BAUD_RATE=115200 -D NUM_HCLK=5 -D HAS_FLASH608K -D RISCV_MEM_48K -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

pll-nanolcd-tangnano9k-synth.json: pll/GW1N-9C-dyn.vh pll-nanolcd/TOP.v pll-nanolcd/VGAMod.v
	$(YOSYS) -D INV_BTN=0 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

pll-nanolcd-tangnano9k.fs: pll-nanolcd-tangnano9k.json
	gowin_pack -c -d GW1N-9C --sspi_as_gpio --mspi_as_gpio -o $@ $^

bsram-%-tangnano9k-synth.json: pll/GW1N-9C-dyn.vh io565.vh display-480x272.v %-image-rom.v %-video-ram.v %.v clock-rPLL.v
	$(YOSYS) -D INV_BTN=0 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

dvi-example-tangnano9k-synth.json: DVI/dvi-example.v DVI/pll480.v DVI/tmds-channel.v
	$(YOSYS) -D INV_BTN=0 -D IS_ELVDS=1 -p "read_verilog -sv $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

# ============================================================
# szfpga miniboard (GW1N-9)
%-miniszfpga.fs: %-miniszfpga.json
	gowin_pack -c -d GW1N-9 -o $@ $<
 
%-miniszfpga.json: %-miniszfpga-synth.json miniszfpga.cst
	$(NEXTPNR) --json $< --write $@ --device GW1N-LV9QN48C6/I5 --vopt family=GW1N-9 --vopt cst=miniszfpga.cst

%-miniszfpga-synth.json: %.v
	$(YOSYS) -D LEDS_NR=4 -D OSC_TYPE_OSC -D INV_BTN=0 -D CPU_FREQ=50 -D BAUD_RATE=115200 -D NUM_HCLK=5 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

blinky-pll-miniszfpga-synth.json: pll/GW1N-9-dyn.vh blinky-pll.v
	$(YOSYS) -D INV_BTN=0 -D LEDS_NR=4 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

bsram-%-miniszfpga-synth.json: pll/GW1N-9-dyn.vh io565.vh display-480x272.v %-image-rom.v %-video-ram.v %.v clock-rPLL.v
	$(YOSYS) -D INV_BTN=0 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

# ============================================================
# szfpga (GW1N-9)
%-szfpga.fs: %-szfpga.json
	gowin_pack -c -d GW1N-9 -o $@ $<
 
%-szfpga.json: %-szfpga-synth.json szfpga.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NR-LV9LQ144PC6/I5 --vopt family=GW1N-9 --vopt cst=szfpga.cst

%-szfpga-synth.json: %.v
	$(YOSYS) -D LEDS_NR=4 -D OSC_TYPE_OSC -D INV_BTN=0 -D CPU_FREQ=50 -D BAUD_RATE=115200 -D NUM_HCLK=5 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

blinky-pll-szfpga-synth.json: pll/GW1N-9-dyn.vh blinky-pll.v
	$(YOSYS) -D INV_BTN=0 -D LEDS_NR=4 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

bsram-%-szfpga-synth.json: pll/GW1N-9-dyn.vh io565.vh display-480x272.v %-image-rom.v %-video-ram.v %.v clock-rPLL.v
	$(YOSYS) -D INV_BTN=0 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

# ============================================================
# tec0117 (GW1N-9)
%-tec0117.fs: %-tec0117.json
	gowin_pack -c -d GW1N-9 -o $@ $<

%-tec0117.json: %-tec0117-synth.json tec0117.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NR-LV9QN88C6/I5 --vopt family=GW1N-9 --vopt cst=tec0117.cst

%-tec0117-synth.json: %.v
	$(YOSYS) -D LEDS_NR=8 -D OSC_TYPE_OSC -D INV_BTN=0 -D CPU_FREQ=12 -D BAUD_RATE=115200 -D NUM_HCLK=5 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

blinky-pll-tec0117-synth.json: pll/GW1N-9-dyn.vh blinky-pll.v
	$(YOSYS) -D INV_BTN=0 -D LEDS_NR=8 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

# ============================================================
# runber (GW1N-4)
%-runber.fs: %-runber.json
	gowin_pack -c -d GW1N-4 -o $@ $<

%-runber.json: %-runber-synth.json runber.cst
	$(NEXTPNR) --json $< --write $@ --device GW1N-UV4LQ144C6/I5 --vopt cst=runber.cst

%-runber-synth.json: %.v
	$(YOSYS) -D LEDS_NR=8 -D OSC_TYPE_OSC -D INV_BTN=0 -D FORCE_BRAM -D CPU_FREQ=12 -D BAUD_RATE=115200 -D NUM_HCLK=5 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

blinky-pll-runber-synth.json: pll/GW1N-4-dyn.vh blinky-pll.v
	$(YOSYS) -D INV_BTN=0 -D LEDS_NR=8 -p "read_verilog $^; synth_gowin -json $@ ${YOSYS_FLAGS}"

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


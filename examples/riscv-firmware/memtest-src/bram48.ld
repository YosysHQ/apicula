MEMORY
{
   BRAM (RWX) : ORIGIN = 0x0000, LENGTH = 0xc000  /* 1800 6kB RAM, 2000 8kB RAM, c000 48kB RAM */
}
SECTIONS
{
    everything :
    {
	. = ALIGN(4);
	start.o (.text)
        *(.*)
	_freeram_start = .; /* for access from program */
    } >BRAM
}
_ram_size = LENGTH(BRAM);

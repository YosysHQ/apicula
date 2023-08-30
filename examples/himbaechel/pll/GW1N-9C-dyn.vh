`define PLL_DYN
`define PLL_DEVICE "GW1NR-9C"
`define PLL_FCLKIN "27"
`define PLL_ODIV_SEL  64

`define PLL_FBDIV_SEL 12
`define PLL_IDIV_SEL  5

`define PLL_FBDIV_SEL_1 9
`define PLL_IDIV_SEL_1  2

// LCD
`define PLL_FBDIV_SEL_LCD 0
`define PLL_IDIV_SEL_LCD  2

// two pll outputs
`define PLL_0_CLKOUT  LCD_CLK
`define PLL_0_CLKOUTD LCD_DEN
`define PLL_0_LOCK    LCD_HYNC
`define PLL_1_CLKOUT  LCD_SYNC
`define PLL_1_CLKOUTD LCD_XR
`define PLL_1_LOCK    LCD_XL

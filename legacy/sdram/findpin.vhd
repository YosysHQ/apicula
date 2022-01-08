library ieee;
use ieee.numeric_std.all;
use ieee.std_logic_1164.all;

entity top is
    port 
    (
        O_sdram_ba : out std_logic_vector(1 downto 1)
    );

end top;

architecture rtl of top is
begin
    O_sdram_ba(1) <= 'Z';
end rtl;

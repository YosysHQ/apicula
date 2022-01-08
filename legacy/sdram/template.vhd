library ieee;
use ieee.numeric_std.all;
use ieee.std_logic_1164.all;

entity top is
    port 
    (
        ##PORT##
    );

end top;

architecture rtl of top is
begin
    ##PORTNAME## <= 'Z';
end rtl;

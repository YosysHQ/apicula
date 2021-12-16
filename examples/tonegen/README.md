# Sigma-delta based tone generator

This project generates a noise-shaped bitstream on one digital output pin.
By connecting an RC low-pass filter to this pin, the analogue sinusoidal signal is recovered from the bitstream, making this a simple method to get an analogue output from a digital pin.

Note: the noise performance of the generator is directly dependent on the digital noise present on the digital pin. For optimal performance, the digital signal should be re-clocked by an external flip-flop (74LV74 or similar). The external flip-flop must have a very clean supply, separate from the FPGA for optimal noise isolation.

A 16-bit input second-order noise shaper is used, which has a limited noise performance, in addition to the power supply noise issue outlined above. Do not expect stellar performance.

A suitable RC reconstruction filter can be made from a 100 ohm resistor and a 1uF capacitor:

                                                                     
```                        
From FPGA                                                                     
         +--------------+                                                     
o--------| R = 100 Ohms |--------|-------------------o   Output
         +--------------+        | 
                                 |                                           
                            +---------+                                                                
                            +---------+  C=1 uFarad                           
                                 |                                            
                                 |                                            
                                 |                                            
                              -------                                         
                               -----                                          
                                ---                                           
```

For the TEC0117 board, the output pin is pin 1 on the 12-pin PMOD header.


## bugs
Using nextpnr-gowin -- Next Generation Place and Route (Version 06d58e6e) and 
Yosys 0.9+4081 (git sha1 c6681508, gcc 9.3.0-17ubuntu1~20.04 -fPIC -Os, it appears that not all phase increments work. See top.v for more information.


il65 - "Intermediate Language for 65xx microprocessors"
-------------------------------------------------------

The python program parses it and generates 6502 assembler code.
It uses the 64tass macro cross assembler to assemble it into binary files.




Memory Model
------------

Zero page:      $00 - $ff
Hardware stack: $100 - $1ff
Free RAM/ROM:   $0200 - $ffff

Reserved:

data direction  $00
bank select     $01
NMI VECTOR      $fffa
RESET VECTOR    $fffc
IRQ VECTOR      $fffe

A particular 6502/6510 machine such as the Commodore-64 will have many other 
special addresses due to:
    - ROMs installed in the machine (basic, kernel and character generator roms)
    - memory-mapped I/O registers (for the video and sound chip for example)
    - RAM areas used for screen graphics and sprite data.


Usable Hardware registers:
    A
    X
    Y
    S  (stack pointer)
    P  (status register)
    PC (program counter, not directly accessible)
    
The zero page locations $02-$ff can be regarded as 254 other registers.
Free zero page addresses on the C-64:
    $02,$03   # reserved as scratch addresses
    $04,$05
    $06
    $0a
    $2a
    $52
    $93
    $f7,$f8
    $f9,$fa
    $fb,$fc
    $fd,$fe



IL program parsing structure:
-----------------------------

@todo


OUTPUT MODES:
-------------
.output raw     ; no load address bytes
.output prg     ; include the first two load address bytes, (default is $0801), no basic program
.output prg,sys ; include the first two load address bytes, basic start program with sys call to code, default code start
                ;   immediately after the basic program at $081d, or beyond.


data types:
    all integers are unsigned...?    @todo signed ints
    bool    true/false   (1/0)
    byte    8 bits      $8f
    int     16 bits     $8fee
    string  0-terminated sequence of bytes  "hello."  (implicit 0-termination byte)  @todo strings
    @todo float?

    
    


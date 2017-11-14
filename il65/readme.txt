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
output raw     ; no load address bytes
output prg     ; include the first two load address bytes, (default is $0801), no basic program
output prg,sys ; include the first two load address bytes, basic start program with sys call to code, default code start
                ;   immediately after the basic program at $081d, or beyond.


data types:
    all integers are unsigned...?    @todo signed ints
    bool    true/false   (1/0)
    byte    8 bits      $8f
    int     16 bits     $8fee
    string  0-terminated sequence of bytes  "hello."  (implicit 0-termination byte)  @todo strings
    @todo float?

    
    
FLOW CONTROL
------------

low level constructs:

- possibility to define local labels (+, -) and goto them (+, ++, +++, - etc)
  @TODO BUT THEN YOU CANNOT NEST THESE.... So: use local symbols (with a seqnr/linenr postfix or something:)
il65_for_999            ; for statement fron line 999
		  ...
_local            ...
		  bne _local
		  ...
il65_for_999_end          ; to close this block of local symbols



- goto with primitive if conditional: directly translates to a branch instruction (ifcc, ifcs, ifvc, ifvs, ifeq, ifne, ifpos, ifmin)
- goto with complex if conditional: where the ifxx is additionally followed by a <condition>
  in that case, evaluate the <condition> first (whatever it is) and then emit a primitive goto with if


IF:

if <cond> {
	...
} else {
	...
}

==> DESUGARING ==>

(no else:)

	goto + ifne <cond>      ; possibly a primitive conditional?
	.... (true part)
+       ; code continues

(with else):

	goto + ifeq <cond>      ; possibly a primitive conditional?
	... (else part)
	goto ++
+       ... (true part)
+       ; code continues


CONDITIONAL:

<var> = <condition>? <truevalue> : <falsevalue>

==> DESUGARING ==>

	goto + ifeq <cond>        ; possibly a primitive conditional?
	var = falsevalue
	goto  ++
+       var = truevalue
+       ; code continues


WHILE:

while <cond> {
	...
	continue
	break
}

==> DESUGARING ==>

	goto +    ; jump to the check  (rest is very similar to REPEAT)
-	... (code)
	goto  -   ;continue
	goto  ++  ;break
+	goto  -  ifeq <cond>    ; loop condition ; possibly a primitive conditional?
+       ; code continues



REPEAT:

repeat {
	...
	continue
	break
} until <cond>

==> DESUGARING ==>

-	... (code)
	goto  -   ; continue
	goto  +   ; break
	goto  - ifne <cond>     ; loop condition ; possibly a primitive conditional?
+       ; code continues



FOR:

for <loopvar> = <from> to <to> [step <step>] {
	...
	break
	continue
}


==> DESUGARING ==>

	loopvar = from
-	goto ++ if loopvar >= to
	goto  ++      ; break
	goto  -       ; continue
	.... (code)
-	loopvar+=step      (if step > 1 or step < -1)
	loopvar++          (if step == 1)
	loopvar--          (if step == -1)
	goto  --         ; end of for loop
+       ; code continues



MEMORY BLOCK OPERATIONS:

@todo
- matrix type operations (whole matrix, per row, per column, individual row/column)
  operations: set, get, copy (from another matrix with the same dimensions, or list with same length),
  shift (up, down, left, right, and diagonals, meant for scrolling)

- list operations (whole list, individual element)
  operations: set, get, copy (from another list with the same length), shift (left,right)

- list and matrix operations ofcourse work identical on vars and on memory mapped vars of these types.


these emit optimized pieces of assembly code, so they run as fast as possible



BITMAP DEFINITIONS:
TO DEFINE CHARACTERS (8x8 monochrome or 4x8 multicolor = 8 bytes)
--> PLACE in memory on correct address
OR SPRITES (24x21 monochrome or 12x21 multicolor = 63 bytes)
--> PLACE in memory on correct address (base+sprite pointer, divisible by 64)

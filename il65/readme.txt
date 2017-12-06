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
    A, X, Y,
    AX, AY, XY (16-bit combined register pairs)
    SC  (status register Carry flag)
    These cannot occur as variable names - they will always refer to the hardware registers.


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


OUTPUT MODES:
-------------
output raw     ; no load address bytes
output prg     ; include the first two load address bytes, (default is $0801), no basic program
output prg,sys ; include the first two load address bytes, basic start program with sys call to code, default code start
                ;   immediately after the basic program at $081d, or beyond.

address $0801   ; override program start address (default is set to $c000 for raw mode and $0801 for c-64 prg mode)
                ; cannot be used if output mode is prg,sys because basic programs always have to start at $0801


data types:
    bool    true/false  (aliases for the integer values 1 and 0, not a true datatype by itself)
    byte    8 bits      $8f    (unsigned, @todo signed bytes)
    int     16 bits     $8fee  (unsigned, @todo signed ints)
    @todo long24 long32?  (and signed)
    string  0-terminated sequence of bytes  "hello."  (implicit 0-termination byte)
    pstring sequence of bytes where first byte is the length. (no 0-termination byte)

    note: floating point numbers are not supported (yet) and will result in a parse error 'invalid number'.
    (maybe in the future the commodore-style 5-byte and perhaps also the apple-style 4-byte float storage formats will be supported)



EXPRESSIONS
-----------

@todo expressions.
@todo allow floating point calculations in the parser in expressions but always truncate them to integer if stored? (like 64tass does)


    
    
FLOW CONTROL
------------

Required building blocks: additional forms of 'go' statement: including an if clause, comparison statement.

- a primitive conditional branch instruction (special case of 'go'): directly translates to a branch instruction:
        if[_XX] go <label>
  XX is one of: (cc, cs, vc, vs, eq, ne, pos, min,
  lt==cc, lts==min,  gt==eq+cs, gts==eq+pos,  le==cc+eq, les==neg+eq,  ge==cs, ges==pos)
  and when left out, defaults to ne (not-zero, i.e. true)
  NOTE: some combination branches such as cc+eq an be peephole optimized see http://www.6502.org/tutorials/compare_beyond.html#2.2

- conditional go with expression: where the if[_XX] is followed by a <expression>
  in that case, evaluate the <expression> first (whatever it is) and then emit the primitive if[_XX] go
        if[_XX] <expression> go <label>
  eventually translates to:
        <expression-code>
        bXX <label>

- comparison statement: compares left with right:  compare <first_value>, <second_value>
  (and keeps the comparison result in the status register.)
  this translates into a lda first_value, cmp second_value sequence after which a conditional branch is possible.



IF_XX:
------
if[_XX] [<expression>] {
        ...
}
[ else {
        ...     ; evaluated when the condition is not met
} ]


==> DESUGARING ==>

(no else:)

                if[_!XX] [<expression>] go il65_if_999_end          ; !XX being the conditional inverse of XX
                .... (true part)
il65_if_999_end ; code continues after this


(with else):
                if[_XX] [<expression>] go il65_if_999
                ... (else part)
                go il65_if_999_end
il65_if_999     ... (true part)
il65_if_999_end ; code continues after this


WHILE:
------
while[_XX] <expression> {
	...
	continue
	break
}

==> DESUGARING ==>

	go il65_while_999_check    ; jump to the check
il65_while_999
	... (code)
	go  il65_while_999          ;continue
	go  il65_while_999_end      ;break
il65_while_999_check
        if[_XX] <expression> go il65_while_999  ; loop condition
il65_while_999_end      ; code continues after this



REPEAT:
------

repeat {
	...
	continue
	break
} until[_XX] <expressoin>

==> DESUGARING ==>

il65_repeat_999
        ... (code)
        go il65_repeat_999          ;continue
        go il65_repeat_999_end      ;break
        if[_!XX] <expression> go il65_repeat_999        ; loop condition via conditional inverse of XX
il65_repeat_999_end         ; code continues after this



FOR:
----

for <loopvar> = <from_expression> to <to_expression> [step <step_expression>] {
	...
	break
	continue
}


@todo how to do signed integer loopvars?


==> DESUGARING ==>

        loopvar = <from_expression>
        compare loopvar, <to_expression>
        if_ge go il65_for_999_end       ; loop condition
        step = <step_expression>        ; (store only if step < -1 or step > 1)
il65_for_999
        go il65_for_999_end        ;break
        go il65_for_999_loop       ;continue
        ....  (code)
il65_for_999_loop
        loopvar += step         ; (if step > 1 or step < -1)
        loopvar++               ; (if step == 1)
        loopvar--               ; (if step == -1)
        go il65_for_999         ; continue the loop
il65_for_999_end        ; code continues after this



MEMORY BLOCK OPERATIONS:

@todo matrix,list,string memory block operations:
- matrix type operations (whole matrix, per row, per column, individual row/column)
  operations: set, get, copy (from another matrix with the same dimensions, or list with same length),
  shift-N (up, down, left, right, and diagonals, meant for scrolling)
  rotate-N (up, down, left, right, and diagonals, meant for scrolling)
  clear (set whole matrix to the given value, default 0)

- list operations (whole list, individual element)
  operations: set, get, copy (from another list with the same length), shift-N(left,right), rotate-N(left,right)
  clear (set whole list to the given value, default 0)

- list and matrix operations ofcourse work identical on vars and on memory mapped vars of these types.

- strings: identical operations as on lists.


these call (or emit inline) optimized pieces of assembly code, so they run as fast as possible



SUBROUTINES AND SUBROUTINE CALLING
----------------------------------

External subroutines for instance defined in ROM, can be defined using the 'subx' statement.

subx   <identifier>    ([proc_parameters]) -> ([proc_results])    <address>

proc_parameters = sequence of "<parametername>:<register>" pairs that specify what the input parameters are
proc_results = sequence of <register> names that specify in which register(s) the output is returned
               if the name ends with a '?', that means the register doesn't contain a real return value but
               is clobbered in the process so the original value it had before calling the sub is no longer valid.

example:  "subx   CLOSE    (logical: A) -> (A?, X?, Y?)       $FFC3"


@todo user defined subroutines


CALLING SUBROUTINES
-------------------

call subroutine and continue afterwards ('gosub'):
        call <subroutine> / <label> / <address>
        @todo call <registerpair> / [<address>]   (indirect)

jump to routine ('goto'):
        go <subroutine> / <label> / <address>
        @todo go <registerpair> / [<address>]   (indirect)


@todo calling syntax such as:   subroutine ([params...])    -->  parse as:   call subroutine [params...]


@todo utilize the subx definiton and support actually calling these external subs via regular calling syntax
@todo support calling user defined subroutines via regular calling syntax and parameter/result calling convention

@todo support args (start with A,X,Y reg args, later named params that go via stack/memory)



BITMAP DEFINITIONS:
to define CHARACTERS (8x8 monochrome or 4x8 multicolor = 8 bytes)
--> PLACE in memory on correct address (???k aligned)
and SPRITES (24x21 monochrome or 12x21 multicolor = 63 bytes)
--> PLACE in memory on correct address (base+sprite pointer, 64-byte aligned)

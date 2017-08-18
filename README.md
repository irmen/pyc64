# pyc64: Commodore-64 "emulator" in pure Python!

![Screenshot one](demo_screenshot1.png)

... Or is it?

Well, it emulates the character mode *with sprites* quite well and thus you can display pretty PETSCII pictures if you want.
It's generally not possible to run actual C-64 software, but that's not the goal
of this project. (Look at actual c-64 emulators such as Vice or CCS64 if you want that)


## 6502 machine code execution

Yes, this thing can actually run 6502 machine code and
has a built-in machine code monitor.
This is made possible by the awesome [py65](https://github.com/mnaberez/py65) library. 
Note that while it can run the 6502 code,
you can only do the same things with it as what is supported
for the BASIC mode. So no fancy screen scrolling or rasterbars...


## BASIC V2 and the VIC-registers (video)

A subset and variant of the BASIC V2 in the C-64 is provided.

Some VIC-II registers have been made available:

- 53280 and 53281 screen and border colors ($d020/$d021)
- 646 cursor color ($0286)
- 1024-2023 the screen buffer characters ($0400-$07e7) 
- 55296-56295 the screen buffer colors ($d800-$dbe7)
- 53272 charset shift/unshift register ($d018)
- the [sprite](https://www.c64-wiki.com/wiki/Sprite) registers! (no multicolor though, and no priority register and collision detection)

A few function keys are remapped as wel for convenience, like the fastloader cartridges of old:

- F1 = LIST:
- F3 = RUN:
- F5 = LOAD shortcut
- F6 (shift-F5): LOAD "*",8  shortcut
- F7 = DOS"$ to show directory of drive8

Note that most of the BASIC operations are essentially handled by Python itself via eval(),
so you can do many interesting things that are silly to see working on a classic 80's c-64 screen.
For instance, try ``print 5**123``  or ``print sys.platform`` or ``print sum(log(x) for x in range(1,10))``

It is not yet supported to do any blocking operation such as INPUT or WAIT.
However, GET *is* supported (which gets one keypress from the keyboard buffer)
So simple interactive programs can be created.


## 1541 disk drive

Rudimentary read-only support for a simulated disk drive is available.
Some demo programs are included 'on the disk' (=the 'drive8' directory),
including some that draw some pretty PETSCII images as seen in the
screenshot.


## Python REPL in your C64

Enter the 'gopy' command to switch to a Python REPL, and use 'go64' to switch back to BASIC.
Some convenience symbols are provided in the REPL to access the screen
and memory for instance. Try 'dir()' to see what's there.


## dependencies

You'll need the [pillow](https://pillow.readthedocs.io) library because 
the program needs to do some charset bitmap conversions at startup for tkinter.

If you want to execute 6502 machine code or inspect the memory via a
machine code monitor, you also need the [py65](https://github.com/mnaberez/py65) library. 


## screenshots

PETSCII image:

![Screenshot two](demo_screenshot2.png)

Python mode:

![Screenshot two](demo_screenshot3.png)


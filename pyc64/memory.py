"""
Commodore-64 Memory representation,
including special functions to handle the (character) screen.

These are integrated because the C-64's screen and colors were
memory-mapped into the memory address space so manipulating bytes of the memory
causes things to happen on the screen immediately.

Written by Irmen de Jong (irmen@razorvine.net)
License: MIT open-source.
"""

import math
import time
import struct
import codecs
from collections import defaultdict
# noinspection PyUnresolvedReferences
import cbmcodecs


def _codec_errors_pyc64specials(error):
    result = []
    for i in range(error.start, error.end):
        replacement = {
                '{': '┤',
                '}': '├',
                '^': '↑',
                '~': '▒',  # PI 'π' in lower-case charset
                'π': '▒',  # PI 'π' in lower-case charset
                '`': "'",
                '_': '▁',
                '|': '│',
                '\\': 'M',  # 'backslash' in lower-case charset
            }.get(error.object[i], None)
        if replacement:
            result.append(replacement)
        else:
            raise error
    return "".join(result), error.end


codecs.register_error("pyc64specials", _codec_errors_pyc64specials)


class Memory:
    """
    A memoryblock (bytes) with read/write intercept possibility,
    to simulate memory-mapped I/O for instance.
    """
    def __init__(self, size=0x10000, endian="little"):
        self.size = size
        self.mem = bytearray(size)
        self.hooked_reads = bytearray(size)   # 'bitmap' of addresses that have read-hooks, for fast checking
        self.hooked_writes = bytearray(size)  # 'bitmap' of addresses that have write-hooks, for fast checking
        self.rom_areas = set()     # set of tuples (start, end) addresses of ROM (read-only) areas
        self.endian = endian     # 'little' or 'big', affects the way 16-bit words are read/written
        self.write_hooks = defaultdict(list)
        self.read_hooks = defaultdict(list)

    def __len__(self):
        return self.size

    def clear(self):
        """set all memory values to 0."""
        for a in range(0, 0x10000):
            self[a] = 0

    def getword(self, address, signed=False):
        """get a 16-bit (2 bytes) value from memory, no aligning restriction"""
        e = "<" if self.endian == "little" else ">"
        s = "h" if signed else "H"
        return struct.unpack(e + s, self[address:address + 2])[0]

    def setword(self, address, value, signed=False):
        """write a 16-bit (2 bytes) value to memory, no aligning restriction"""
        e = "<" if self.endian == "little" else ">"
        s = "h" if signed else "H"
        self[address:address + 2] = struct.pack(e + s, value)

    def getlong(self, address, signed=False):
        """get a 32-bit (4 bytes) value from memory, no aligning restriction"""
        e = "<" if self.endian == "little" else ">"
        s = "i" if signed else "I"
        return struct.unpack(e + s, self[address:address + 4])[0]

    def setlong(self, address, value, signed=False):
        """write a 32-bit (4 bytes) value to memory, no aligning restriction"""
        e = "<" if self.endian == "little" else ">"
        s = "i" if signed else "I"
        self[address:address + 4] = struct.pack(e + s, value)

    def __getitem__(self, addr_or_slice):
        """get the value of a memory location or range of locations (via slice)"""
        if type(addr_or_slice) is int:
            if self.hooked_reads[addr_or_slice]:
                value = self.mem[addr_or_slice]
                for hook in self.read_hooks[addr_or_slice]:
                    newvalue = hook(addr_or_slice, value)
                    if newvalue is not None:
                        value = newvalue
                self.mem[addr_or_slice] = value
            return self.mem[addr_or_slice]
        elif type(addr_or_slice) is slice:
            if any(self.hooked_reads[addr_or_slice]):
                # there's at least one address in the slice with a hook, so... slow mode
                return [self[addr] for addr in range(*addr_or_slice.indices(self.size))]
            else:
                # there's no address in the slice that's hooked so we can return it fast
                return self.mem[addr_or_slice]
        else:
            raise TypeError("invalid address type")

    def __setitem__(self, addr_or_slice, value):
        """set the value of a memory location or range of locations (via slice)"""
        if type(addr_or_slice) is int:
            if self.hooked_writes[addr_or_slice]:
                for hook in self.write_hooks[addr_or_slice]:
                    newvalue = hook(addr_or_slice, self.mem[addr_or_slice], value)
                    if newvalue is not None:
                        value = newvalue
            if self.rom_areas:
                self._write_with_romcheck_addr(addr_or_slice, value)
            else:
                self.mem[addr_or_slice] = value
        elif type(addr_or_slice) is slice:
            if any(self.hooked_writes[addr_or_slice]):
                # there's at least one address in the slice with a hook, so... slow mode
                if type(value) is int:
                    for addr in range(*addr_or_slice.indices(self.size)):
                        self[addr] = value
                else:
                    slice_range = range(*addr_or_slice.indices(self.size))
                    if len(slice_range) != len(value):
                        raise ValueError("value length differs from memory slice length")
                    for addr, value in zip(slice_range, value):
                        self[addr] = value
            else:
                # there's no address in the slice that's hooked so we can write fast
                slice_len = len(range(*addr_or_slice.indices(self.size)))
                if type(value) is int:
                    value = bytes([value]) * slice_len
                elif len(value) != slice_len:
                    raise ValueError("value length differs from memory slice length")
                if self.rom_areas:
                    self._write_with_romcheck_slice(addr_or_slice, value)
                else:
                    self.mem[addr_or_slice] = value
        else:
            raise TypeError("invalid address type")

    def _write_with_romcheck_addr(self, address, value):
        for rom_start, rom_end in self.rom_areas:
            if address >= rom_start and address <= rom_end:
                return   # don't write to ROM address
        self.mem[address] = value

    def _write_with_romcheck_slice(self, addrslice, value):
        for rom_start, rom_end in self.rom_areas:
            if addrslice.start <= rom_end and addrslice.stop >= rom_start+1:
                # the slice could be *partially* in RAM and *partially* in ROM
                # we're not figuring that out here, just write/check every byte individually.
                if type(value) is int:
                    for addr in range(*addrslice.indices(self.size)):
                        self[addr] = value
                else:
                    slice_range = range(*addrslice.indices(self.size))
                    if len(slice_range) != len(value):
                        raise ValueError("value length differs from memory slice length")
                    for addr, value in zip(slice_range, value):
                        self[addr] = value
                return
        # whole slice is outside of all rom areas, just write it
        self.mem[addrslice] = value

    def intercept_write(self, address, hook):
        """
        Register a hook function to be called when a write occurs to the given memory address.
        The function(addr, oldval, newval) can return a modified value to be written.
        """
        self.write_hooks[address].append(hook)
        self.hooked_writes[address] = 1

    def intercept_read(self, address, hook):
        """
        Register a hook function to be called when a read occurs of the given memory address.
        The function(addr, value) can return a modified value to be the result of the read.
        """
        self.read_hooks[address].append(hook)
        self.hooked_reads[address] = 1

    def load_rom(self, romfile, address):
        with open(romfile, "rb") as romf:
            data = romf.read()
            self.mem[address:address+len(data)] = data
            self.rom_areas.add((address, address+len(data)-1))

    def _patch(self, address, value):
        # hard overwrite a value, don't do ROM check, no callbacks
        self.mem[address] = value


class ScreenAndMemory:
    colorpalette_morecontrast = (       # this is a palette with more contrast
        0x000000,  # 0 = black
        0xFFFFFF,  # 1 = white
        0x68372B,  # 2 = red
        0x70A4B2,  # 3 = cyan
        0x6F3D86,  # 4 = purple
        0x588D43,  # 5 = green
        0x352879,  # 6 = blue
        0xB8C76F,  # 7 = yellow
        0x6F4F25,  # 8 = orange
        0x433900,  # 9 = brown
        0x9A6759,  # 10 = light red
        0x444444,  # 11 = dark grey
        0x6C6C6C,  # 12 = medium grey
        0x9AD284,  # 13 = light green
        0x6C5EB5,  # 14 = light blue
        0x959595,  # 15 = light grey
    )
    colorpalette_pepto = (         # this is Pepto's Commodore-64 palette  http://www.pepto.de/projects/colorvic/
        0x000000,  # 0 = black
        0xFFFFFF,  # 1 = white
        0x813338,  # 2 = red
        0x75cec8,  # 3 = cyan
        0x8e3c97,  # 4 = purple
        0x56ac4d,  # 5 = green
        0x2e2c9b,  # 6 = blue
        0xedf171,  # 7 = yellow
        0x8e5029,  # 8 = orange
        0x553800,  # 9 = brown
        0xc46c71,  # 10 = light red
        0x4a4a4a,  # 11 = dark grey
        0x7b7b7b,  # 12 = medium grey
        0xa9ff9f,  # 13 = light green
        0x706deb,  # 14 = light blue
        0xb2b2b2,  # 15 = light grey
    )
    colorpalette_light = (                    # this is a lighter palette
        0x000000,   # 0 = black
        0xFFFFFF,   # 1 = white
        0x984B43,   # 2 = red
        0x79C1C8,   # 3 = cyan
        0x9B51A5,   # 4 = purple
        0x68AE5C,   # 5 = green
        0x52429D,   # 6 = blue
        0xC9D684,   # 7 = yellow
        0x9B6739,   # 8 = orange
        0x6A5400,   # 9 = brown
        0xC37B75,   # 10 = light red
        0x636363,   # 11 = dark grey
        0x8A8A8A,   # 12 = medium grey
        0xA3E599,   # 13 = light green
        0x8A7BCE,   # 14 = light blue
        0xADADAD,   # 15 = light grey
    )

    def __init__(self, columns=40, rows=25, sprites=8, rom_directory=""):
        # zeropage is from $0000-$00ff
        # screen chars     $0400-$07ff
        # screen colors    $d800-$dbff
        self.memory = Memory(65536)    # 64 Kb
        self.using_roms = False
        if rom_directory:
            for rom, address in (("basic", 0xa000), ("kernal", 0xe000)):
                try:
                    self.memory.load_rom(rom_directory+"/"+rom, address)
                    print("loading rom file", rom, "at", hex(address))
                    self.using_roms = True
                except IOError:
                    print("can't load rom-file {:s}/{:s}, consider supplying it".format(rom_directory, rom))
            # apply some ROM patches to make the reset routine work on the simulator:
            self.memory._patch(0xe388, 0x4c)   # JMP to same address near the end of the reset routine
            self.memory._patch(0xe389, 0x88)   # ...to avoid entering actual basic program loop. RTS won't work because the stack is clobbered I think.
            self.memory._patch(0xe38a, 0xe3)   # ...(this jmp loop is recognised by tahe cpu emulator as an 'end of the program')
            # self.memory._patch(0xfce5, 0xea)   # NOP to not clobber stack pointer register in reset routine
            self.memory._patch(0xfcf6, 0x90)   # skip a large part of the memory init routine that is very slow and may cause issues
        self.hz = 60        # NTSC
        self.columns = columns
        self.rows = rows
        self.sprites = sprites
        self.reset(True)
        self.install_memory_hooks()

    def install_memory_hooks(self):
        def write_screencolor(address, oldval, newval):
            self._full_repaint |= oldval != newval

        def write_shifted(address, oldval, newval):
            self._full_repaint |= bool((oldval & 2) ^ (newval & 2))

        def read_jiffieclock(address, value):
            jiffies = int(self.hz * (time.perf_counter() - self.jiffieclock_epoch)) % (24 * 3600 * self.hz)
            if address == 160:
                return (jiffies >> 16) & 0xff
            if address == 161:
                return (jiffies >> 8) & 0xff
            return jiffies & 0xff

        def write_jiffieclock(address, oldval, newval):
            jiffies = int(self.hz * (time.perf_counter() - self.jiffieclock_epoch)) & 0xffffff
            if address == 160:
                jiffies = (jiffies & 0x00ffff) | (newval << 16)
            elif address == 161:
                jiffies = (jiffies & 0xff00ff) | (newval << 8)
            else:
                jiffies = (jiffies & 0xffff00) | newval
            if jiffies > self.hz * 24 * 3600:
                jiffies = 0
                newval = 0
                if address == 160:
                    self.memory[161], self.memory[162] = 0, 0
                elif address == 161:
                    self.memory[160], self.memory[162] = 0, 0
                else:
                    self.memory[160], self.memory[161] = 0, 0
                self.jiffieclock_epoch = time.perf_counter()
            self.jiffieclock_epoch = time.perf_counter() - jiffies / self.hz
            return newval

        def write_controlregister(address, oldval, newval):
            pass

        def read_controlregister(address, value):
            # the high bit of the control register is bit#9 of the raster beam position (0-319)
            frac, _ = math.modf(time.time() * self.hz)
            if 320 * frac > 255:
                return value | 0x80
            return value & 0x7f

        def read_raster(address, value):
            # the raster beam position which goes from 0-319 every 1/hz second
            # this register contains the low 8 bits of this value
            frac, _ = math.modf(time.time() * self.hz)
            return int(320 * frac) % 255

        self.memory.intercept_read(160, read_jiffieclock)
        self.memory.intercept_read(161, read_jiffieclock)
        self.memory.intercept_read(162, read_jiffieclock)
        self.memory.intercept_write(160, write_jiffieclock)
        self.memory.intercept_write(161, write_jiffieclock)
        self.memory.intercept_write(162, write_jiffieclock)
        self.memory.intercept_write(53272, write_shifted)
        self.memory.intercept_write(53281, write_screencolor)
        self.memory.intercept_write(53270, write_controlregister)
        self.memory.intercept_write(53265, write_controlregister)
        self.memory.intercept_read(53265, read_controlregister)
        self.memory.intercept_read(53266, read_raster)

    def reset(self, hard=False):
        self._full_repaint = True
        self._shifted = False
        self.inversevid = False
        self.cursor = 0
        self.cursor_state = False
        self.cursor_blink_rate = 300
        self._cursor_enabled = True
        self._previous_checked_chars = bytearray(self.columns * self.rows)
        self._previous_checked_colors = bytearray(self.columns * self.rows)
        if hard:
            self.memory.clear()
        # initialize the zero page and stack with a dump of the values of these pages from a running c64 memory dump
        self.memory[0x0000:0x0200] = [0x2f, 0x37, 0x00, 0xaa, 0xb1, 0x91, 0xb3, 0x22, 0x22, 0x00, 0x00, 0x00, 0x00, 0xff, 0x00, 0x00,
                                      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x19, 0x16, 0x00, 0x0a, 0x76, 0xa3, 0x00, 0x00, 0x00, 0x00,
                                      0x00, 0x00, 0x76, 0xa3, 0xb3, 0xbd, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x08, 0x03, 0x08, 0x03,
                                      0x08, 0x03, 0x08, 0x00, 0xa0, 0x00, 0x00, 0x00, 0xa0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                      0x00, 0x00, 0x08, 0x00, 0x00, 0x00, 0x00, 0x24, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                      0x00, 0x00, 0x00, 0x03, 0x4c, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xfc, 0x00, 0x00,
                                      0x00, 0x0a, 0x76, 0xa3, 0x19, 0x00, 0x20, 0x00, 0x00, 0x80, 0x00, 0x00, 0x00, 0x04, 0x00, 0x76,
                                      0x00, 0x80, 0xa3, 0xe6, 0x7a, 0xd0, 0x02, 0xe6, 0x7b, 0xad, 0x00, 0x08, 0xc9, 0x3a, 0xb0, 0x0a,
                                      0xc9, 0x20, 0xf0, 0xef, 0x38, 0xe9, 0x30, 0x38, 0xe9, 0xd0, 0x60, 0x80, 0x4f, 0xc7, 0x52, 0x58,
                                      0x00, 0xff, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00, 0x80, 0x00, 0x00,
                                      0x00, 0x01, 0xbf, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                      0x00, 0x00, 0x3c, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                      0x00, 0x00, 0xa0, 0x30, 0xfd, 0x40, 0x00, 0x00, 0x00, 0x06, 0x00, 0x40, 0x00, 0x01, 0x20, 0x01,
                                      0x00, 0xf0, 0x04, 0x00, 0x00, 0x27, 0x06, 0x85, 0x00, 0x84, 0x84, 0x84, 0x84, 0x84, 0x84, 0x84,
                                      0x85, 0x85, 0x85, 0x85, 0x85, 0x85, 0x86, 0x86, 0x86, 0x86, 0x86, 0x86, 0x86, 0x87, 0x87, 0x87,
                                      0x87, 0x87, 0x87, 0xf0, 0xd8, 0x81, 0xeb, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x20,
                                      0x33, 0x38, 0x39, 0x31, 0x31, 0x00, 0x30, 0x30, 0x30, 0x30, 0x03, 0x8d, 0x94, 0x9e, 0xa9, 0x00,
                                      0x8d, 0x00, 0xde, 0x60, 0xa0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                      0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
                                      0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
                                      0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
                                      0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
                                      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                      0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
                                      0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
                                      0xff, 0xff, 0xff, 0xff, 0x3f, 0x7d, 0xea, 0x7d, 0xea, 0x20, 0x07, 0xff, 0x7d, 0xea, 0x85, 0x01,
                                      0x00, 0x22, 0xd4, 0xe5, 0x00, 0x0a, 0x14, 0xe1, 0x64, 0xa5, 0x85, 0xa4, 0x79, 0xa6, 0x9c, 0xe3]
        self.memory[0x0200:0x0300] = bytearray(256)   # clear the third page
        if hard:
            # from $0800-$ffff we have a 00/FF pattern alternating every 64 bytes
            for m in range(0x0840, 0x10000, 128):
                self.memory[m: m + 64] = b"\xff" * 64
        self.memory[0xd000:0xd031] = bytearray(0x31)   # wipe VIC registers
        self.memory[0xd027:0xd02f] = [1, 2, 3, 4, 5, 6, 7, 12]    # initial sprite colors
        self.memory[0x07f8:0x0800] = [255, 255, 255, 255, 255, 255, 255, 255]   # sprite pointers
        self.memory[0xd018] = 21
        self.memory.setword(0x002b, 0x0801)  # basic start
        self.memory.setword(0x0031, 0x0803)  # begin of free basic ram
        self.memory.setword(0x0033, 0xa000)  # end of free basic ram
        self.memory.setword(0x0281, 0x0800)  # basic start
        self.memory.setword(0x0283, 0xa000)  # basic end
        self.memory[0x0288] = 0x0400 // 256   # screen buffer pointer
        self.memory[0x02a6] = 1    # we're a PAL machine
        self.memory[0xd011] = 27   # Vic control register 1 (yscroll etc)
        self.memory[0xd016] = 200  # Vic control register 2 (xscroll etc)
        if (0xa000, 0xbfff) not in self.memory.rom_areas:
            self.memory[0xa000:0xc000] = 96    # basic ROM are all RTS instructions (in case no ROM file is present)
        if (0xe000, 0xffff) not in self.memory.rom_areas:
            self.memory[0xe000:0x10000] = 96   # kernal ROM are all RTS instructions (in case no ROM file is present)
        self.jiffieclock_epoch = time.perf_counter()
        self.border = 14
        self.screen = 6
        self.text = 14
        self.joy_fire = self.joy_up = self.joy_down = self.joy_left = self.joy_right =\
            self.joy_leftup = self.joy_rightup = self.joy_leftdown = self.joy_rightdown = False
        self.memory[56320] = 0b01111111   # joystick port 2
        self.memory[56321] = 0b01111111   # joystick port 1 (not used)
        self.clear()

    @property
    def screen(self):
        return self.memory[53281]

    @screen.setter
    def screen(self, color):
        self.memory[53281] = color
        self._full_repaint = True

    @property
    def border(self):
        return self.memory[53280]

    @border.setter
    def border(self, color):
        self.memory[53280] = color

    @property
    def text(self):
        return self.memory[646]

    @text.setter
    def text(self, color):
        self.memory[646] = color

    @property
    def csel38(self):
        return not (self.memory[53270] & 8)

    @csel38.setter
    def csel38(self, value):
        self.memory[53270] |= 0 if value else 8

    @property
    def rsel24(self):
        return not (self.memory[53265] & 8)

    @rsel24.setter
    def rsel24(self, value):
        self.memory[53265] |= 0 if value else 8

    @property
    def shifted(self):
        return bool(self.memory[53272] & 2)

    @shifted.setter
    def shifted(self, value):
        if value:
            self.memory[53272] |= 2
        else:
            self.memory[53272] &= ~2

    @property
    def scrollx(self):
        return self.memory[53270] & 7

    @scrollx.setter
    def scrollx(self, value):
        self.memory[53270] = (self.memory[53270] & 248) | (value & 7)

    @property
    def scrolly(self):
        return self.memory[53265] & 7

    @scrolly.setter
    def scrolly(self, value):
        self.memory[53265] = (self.memory[53265] & 248) | (value & 7)

    @property
    def cursor_enabled(self):
        return self._cursor_enabled

    @cursor_enabled.setter
    def cursor_enabled(self, enabled):
        if not enabled:
            self._fix_cursor(False)
        self._cursor_enabled = enabled

    def hztick(self):
        # called periodically, ideally 50hz or 60hz (PAL/NTSC) (but may be less)
        pass

    class Sprite:
        x = 0
        y = 0
        enabled = False
        doublex = False
        doubley = False
        color = 0
        pointer = 0
        bitmap = None

    def getsprites(self, which=None, bitmap=True):
        # return all data of one or more sprites (in a dict)
        colors = self.memory[0xd027:0xd02f]
        pos = self.memory[0xd000:0xd010]
        xmsb = self.memory[0xd010]
        doublex = self.memory[0xd01d]
        doubley = self.memory[0xd017]
        enabled = self.memory[0xd015]
        pointers = self.memory[0x07f8:0x0800]
        if which is None:
            which = range(self.sprites)
        else:
            assert all(0 <= i <= (self.sprites - 1) for i in which)
        result = {}
        for i in which:
            s = ScreenAndMemory.Sprite()
            s.color = colors[i]
            s.x = pos[i * 2] + (256 if xmsb & 1 << i else 0)
            s.y = pos[1 + i * 2]
            s.doublex = bool(doublex & 1 << i)
            s.doubley = bool(doubley & 1 << i)
            s.enabled = bool(enabled & 1 << i)
            s.pointer = pointers[i] * 64
            if bitmap:
                s.bitmap = self.memory[s.pointer: s.pointer + 63]
            result[i] = s
        return result

    def setspritecolor(self, spritenum, color):
        assert 0 <= spritenum <= self.sprites - 1
        assert 0 <= color <= 255
        self.memory[0xd027 + spritenum] = color

    def setspritepos(self, spritenum, x, y):
        assert 0 <= spritenum <= self.sprites - 1
        self.memory[0xd000 + spritenum] = x & 255
        self.memory[0xd001 + spritenum] = y
        if x > 255:
            self.memory[0xd010] |= 1 << spritenum
        else:
            self.memory[0xd010] &= ~ (1 << spritenum)

    def getchar(self, x, y):
        """get the character AND color value at position x,y"""
        assert 0 <= x <= self.columns and 0 <= y <= self.rows, "position out of range"
        offset = x + y * self.columns
        return self.memory[0x0400 + offset], self.memory[0xd800 + offset]

    def blink_cursor(self):
        if self.cursor_enabled:
            self.cursor_state = not self.cursor_state
            if self.cursor_state:
                self.memory[0x0287] = self.memory[0xd800 + self.cursor]   # save char color to GDCOL memory address
                self.memory[0xd800 + self.cursor] = self.text
            else:
                self.memory[0xd800 + self.cursor] = self.memory[0x0287]   # restore char color from GDCOL address
            self.memory[0x0400 + self.cursor] ^= 0x80

    def writestr(self, txt):
        """Write ASCII text to the screen."""
        # Convert ascii to petscii. Lower-case codec is used.
        self.write(bytes(txt, "petscii-c64en-lc", "pyc64specials"))

    @classmethod
    def _petscii2screen(cls, petscii_code, inversevid=False):
        if petscii_code <= 0x0f:
            code = petscii_code + 128
        elif petscii_code <= 0x3f:
            code = petscii_code
        elif petscii_code <= 0x5f:
            code = petscii_code - 64
        elif petscii_code <= 0x7f:
            code = petscii_code - 32
        elif petscii_code <= 0x9f:
            code = petscii_code + 64
        elif petscii_code <= 0xbf:
            code = petscii_code - 64
        elif petscii_code <= 0xfe:
            code = petscii_code - 128
        else:
            code = 94
        if inversevid:
            return code | 0x80
        return code

    def write(self, petscii):
        """Write PETSCII-encoded text to the screen."""
        assert isinstance(petscii, bytes)
        self._fix_cursor()
        petscii = petscii.replace(b"\x8d", b"\x0d")    # replace shift-RETURN by regular RETURN
        txtcolors = {
            0x05: 1,  # white
            0x1c: 2,  # red
            0x1e: 5,  # green
            0x1f: 6,  # blue
            0x81: 8,  # orange
            0x90: 0,  # black
            0x95: 9,  # brown
            0x96: 10,  # pink/light red
            0x97: 11,  # dark grey
            0x98: 12,  # grey
            0x99: 13,  # light green
            0x9a: 14,  # light blue
            0x9b: 15,  # light grey
            0x9c: 4,  # purple
            0x9e: 7,  # yellow
            0x9f: 3,  # cyan
        }
        non_printable = {0, 1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 15, 16,
                         21, 22, 23, 24, 25, 26, 27, 128, 130, 131, 132,
                         133, 134, 135, 136, 137, 138, 139, 140, 143}

        def handle_special(c):
            # note: return/shift-return are handled automatically
            if c in txtcolors:
                self.text = txtcolors[c]
            elif c == 0x0d:
                # RETURN, go to next line
                self.cursor = self.columns * (1 + self.cursor // self.columns)
                if self.cursor > self.columns * (self.rows - 1):
                    self._scroll_up()
                    self.cursor = self.columns * (self.rows - 1)
                # also, disable inverse-video
                self.inversevid = False
            elif c == 0x0e:
                self._shifted = True
            elif c == 0x8e:
                self._shifted = False
            elif c == 0x11:
                self.down()
            elif c == 0x91:
                self.up()
            elif c == 0x1d:
                self.right()
            elif c == 0x9d:
                self.left()
            elif c == 0x12:
                self.inversevid = True
            elif c == 0x92:
                self.inversevid = False
            elif c == 0x13:
                self.cursormove(0, 0)   # home
            elif c == 0x14:
                self.backspace()
            elif c == 0x94:
                self.insert()
            elif c == 0x93:
                self.clear()
            else:
                return False
            return True

        prev_cursor_enabled = self._cursor_enabled
        self._cursor_enabled = False
        for c in petscii:
            if c in non_printable:
                continue
            if not handle_special(c):
                self.memory[0x0400 + self.cursor] = self._petscii2screen(c, self.inversevid)
                self.memory[0xd800 + self.cursor] = self.text
                self.cursor += 1
                if self.cursor >= self.columns * self.rows:
                    self._scroll_up()
                    self.cursor = self.columns * (self.rows - 1)
        self._cursor_enabled = prev_cursor_enabled
        self._fix_cursor(True)

    def _fix_cursor(self, on=False):
        if on and not self.cursor_enabled:
            return
        if not on and self.cursor_state:
            self.memory[0x0400 + self.cursor] &= 0x7f
            self.memory[0xd800 + self.cursor] = self.memory[0x0287]  # restore char color from GDCOL
        if on and not self.cursor_state:
            self.memory[0x0287] = self.memory[0xd800 + self.cursor]  # save char color to GDCOL address
            self.memory[0x0400 + self.cursor] |= 0x80
            self.memory[0xd800 + self.cursor] = self.text
        self.cursor_state = on

    def _calc_scroll_params(self, topleft, bottomright, fill):
        if topleft is None:
            topleft = (0, 0)
        if bottomright is None:
            bottomright = (self.columns - 1, self.rows - 1)
        width = bottomright[0] - topleft[0] + 1
        height = bottomright[1] - topleft[1] + 1
        fillchar = fill[0]
        fillcolor = self.text if fill[1] is None else fill[1]
        chars_start = 0x0400 + topleft[0] + topleft[1] * self.columns
        colors_start = chars_start + 0xd400
        return width, height, fillchar, fillcolor, chars_start, colors_start

    def _scroll_up(self, topleft=None, bottomright=None, fill=(32, None), amount=1):
        width, height, fillchar, fillcolor, chars_start, colors_start = self._calc_scroll_params(topleft, bottomright, fill)
        amount = min(amount, height)
        if width == self.columns:
            # Full width of screen; can be done with single slice assignments.
            self.memory[chars_start: chars_start + self.columns * (height - amount)] =\
                self.memory[chars_start + self.columns * amount: chars_start + self.columns * height]
            self.memory[colors_start: colors_start + self.columns * (height - amount)] =\
                self.memory[colors_start + self.columns * amount: colors_start + self.columns * height]
            self.memory[chars_start + self.columns * (height - amount): chars_start + self.columns * height] = fillchar
            self.memory[colors_start + self.columns * (height - amount): colors_start + self.columns * height] = fillcolor
        else:
            # we must scroll a part of the screen, this must be done on a per-line basis.
            for y in range(0, height - amount):
                self.memory[chars_start + self.columns * y: chars_start + width + self.columns * y] =\
                    self.memory[chars_start + self.columns * (y + amount): chars_start + width + self.columns * (y + amount)]
                self.memory[colors_start + self.columns * y: colors_start + width + self.columns * y] =\
                    self.memory[colors_start + self.columns * (y + amount): colors_start + width + self.columns * (y + amount)]
            for y in range(height - amount, height):
                self.memory[chars_start + self.columns * y: chars_start + width + self.columns * y] = fillchar
                self.memory[colors_start + self.columns * y: colors_start + width + self.columns * y] = fillcolor

    def _scroll_down(self, topleft=None, bottomright=None, fill=(32, None), amount=1):
        width, height, fillchar, fillcolor, chars_start, colors_start = self._calc_scroll_params(topleft, bottomright, fill)
        amount = min(amount, height)
        if width == self.columns:
            # Full width of screen; can be done with single slice assignments.
            self.memory[chars_start + self.columns * amount: chars_start + self.columns * height] =\
                self.memory[chars_start: chars_start + self.columns * (height - amount)]
            self.memory[colors_start + self.columns * amount: colors_start + self.columns * height] =\
                self.memory[colors_start: colors_start + self.columns * (height - amount)]
            self.memory[chars_start: chars_start + self.columns * amount] = fillchar
            self.memory[colors_start: colors_start + self.columns * amount] = fillcolor
        else:
            # we must scroll a part of the screen, this must be done on a per-line basis.
            for y in range(height - 1, amount - 1, -1):
                self.memory[chars_start + self.columns * y: chars_start + width + self.columns * y] =\
                    self.memory[chars_start + self.columns * (y - amount): chars_start + width + self.columns * (y - amount)]
                self.memory[colors_start + self.columns * y: colors_start + width + self.columns * y] =\
                    self.memory[colors_start + self.columns * (y - amount): colors_start + width + self.columns * (y - amount)]
            for y in range(0, amount):
                self.memory[chars_start + self.columns * y: chars_start + width + self.columns * y] = fillchar
                self.memory[colors_start + self.columns * y: colors_start + width + self.columns * y] = fillcolor

    def _scroll_left(self, topleft=None, bottomright=None, fill=(32, None), amount=1):
        width, height, fillchar, fillcolor, chars_start, colors_start = self._calc_scroll_params(topleft, bottomright, fill)
        amount = min(amount, width)
        for y in range(0, height):
            self.memory[chars_start + self.columns * y: chars_start + self.columns * y + width - amount] = \
                self.memory[chars_start + self.columns * y + amount: chars_start + self.columns * y + width]
            self.memory[colors_start + self.columns * y: colors_start + self.columns * y + width - amount] = \
                self.memory[colors_start + self.columns * y + amount: colors_start + self.columns * y + width]
        for x in range(width - amount, width):
            self.memory[chars_start + x: chars_start + x + self.columns * height: self.columns] = fillchar
            self.memory[colors_start + x: colors_start + x + self.columns * height: self.columns] = fillcolor

    def _scroll_right(self, topleft=None, bottomright=None, fill=(32, None), amount=1):
        width, height, fillchar, fillcolor, chars_start, colors_start = self._calc_scroll_params(topleft, bottomright, fill)
        amount = min(amount, width)
        for y in range(0, height):
            self.memory[chars_start + amount + self.columns * y: chars_start + self.columns * y + width] = \
                self.memory[chars_start + self.columns * y: chars_start + self.columns * y + width - amount]
            self.memory[colors_start + amount + self.columns * y: colors_start + self.columns * y + width] = \
                self.memory[colors_start + self.columns * y: colors_start + self.columns * y + width - amount]
        for x in range(amount):
            self.memory[chars_start + x: chars_start + x + self.columns * height: self.columns] = fillchar
            self.memory[colors_start + x: colors_start + x + self.columns * height: self.columns] = fillcolor

    def scroll(self, topleft, bottomright, up=False, down=False, left=False, right=False, fill=(32, None), amount=1):
        self._fix_cursor()
        if up:
            self._scroll_up(topleft, bottomright, fill, amount)
        if down:
            self._scroll_down(topleft, bottomright, fill, amount)
        if left:
            self._scroll_left(topleft, bottomright, fill, amount)
        if right:
            self._scroll_right(topleft, bottomright, fill, amount)
        self._fix_cursor(True)

    def return_key(self):
        self._fix_cursor()
        self.cursor = self.columns * (self.cursor // self.columns) + self.columns
        if self.cursor >= self.columns * self.rows:
            self._scroll_up()
            self.cursor -= self.columns
        self._fix_cursor(on=True)

    def backspace(self):
        if self.cursor > 0:
            self._fix_cursor()
            self.cursor -= 1
            end = self.columns * (self.cursor // self.columns) + self.columns - 1
            self.memory[0x0400 + self.cursor: 0x0400 + end] = self.memory[0x0400 + self.cursor + 1: 0x0400 + end + 1]
            self.memory[0xd800 + self.cursor: 0xd800 + end] = self.memory[0xd800 + self.cursor + 1: 0xd800 + end + 1]
            self.memory[0x0400 + end] = 32
            self.memory[0xd800 + end] = self.text
            self._fix_cursor(on=True)

    def insert(self):
        if self.cursor < self.columns * self.rows - 1:
            self._fix_cursor()
            end = self.columns * (self.cursor // self.columns) + self.columns
            self.memory[0x0400 + self.cursor + 1: 0x0400 + end] = self.memory[0x0400 + self.cursor: 0x0400 + end - 1]
            self.memory[0xd800 + self.cursor + 1: 0xd800 + end] = self.memory[0xd800 + self.cursor: 0xd800 + end - 1]
            self.memory[0x0400 + self.cursor] = 32
            self.memory[0xd800 + self.cursor] = self.text
            self._fix_cursor(on=True)

    def up(self):
        self._fix_cursor()
        if self.cursor < self.columns:
            self._scroll_down()
        else:
            self.cursor -= self.columns
        self._fix_cursor(on=True)

    def down(self):
        self._fix_cursor()
        if self.cursor >= self.columns * (self.rows - 1):
            self._scroll_up()
        else:
            self.cursor += self.columns
        self._fix_cursor(on=True)

    def left(self):
        if self.cursor > 0:
            self._fix_cursor()
            self.cursor -= 1
            self._fix_cursor(on=True)

    def right(self):
        if self.cursor < self.columns * self.rows:
            self._fix_cursor()
            self.cursor += 1
            self._fix_cursor(on=True)

    def clear(self):
        # clear the screen buffer
        self.memory[0x0400: 0x0400 + self.columns * self.rows] = 32
        self.memory[0xd800: 0xd800 + self.columns * self.rows] = self.text
        self.cursor = 0
        self._fix_cursor(on=True)

    def cursormove(self, x, y):
        self._fix_cursor()
        self.cursor = x + self.columns * y
        self._fix_cursor(on=True)

    def cursorpos(self):
        row, col = divmod(self.cursor, self.columns)
        return col, row

    def current_line(self, include_previous=False, include_next=False, format="screencodes"):
        start_y = end_y = self.cursor // self.columns
        if include_previous:
            start_y = max(0, start_y - 1)
        if include_next:
            end_y = min(self.rows, end_y + 1)
        self._fix_cursor()
        screencodes = self.memory[0x0400 + self.columns * start_y: 0x0400 + self.columns * (end_y + 1)]
        self._fix_cursor()
        if format == "ascii":
            # use the cbmcodec to translate screen codes back into ASCII
            screencodes = bytes(sc & 0x7f for sc in screencodes)        # get rid of reverse-video
            return str(screencodes, "screencode-c64-lc")
        elif format == "petscii":
            # use a simple translation table to translate screen codes into petscii codes
            screencodes = bytes(sc & 0x7f for sc in screencodes)        # get rid of reverse-video
            result = []
            for sc in screencodes:
                if sc <= 0x1f:
                    result.append(sc + 64)
                elif sc <= 0x3f:
                    result.append(sc)
                else:
                    result.append(sc + 32)
            return bytes(result)
        elif format == "screencodes":
            return screencodes
        else:
            raise ValueError("invalid format: " + format)

    def getdirty(self):
        # this is pretty fast, on my machine about 0.001 second to diff a 64x50 screen (3200 chars)
        # it usually is worth this extra millisecond because it can give huge savings
        # in the actual screen redraw part
        chars = self.memory[0x0400: 0x0400 + self.columns * self.rows]
        colors = self.memory[0xd800: 0xd800 + self.columns * self.rows]
        prev_chars = self._previous_checked_chars
        prev_colors = self._previous_checked_colors

        if self._full_repaint:
            self._full_repaint = False
            result = [(i, (chars[i], colors[i])) for i in range(self.columns * self.rows)]
        else:
            result = [(i, (chars[i], colors[i])) for i in range(self.columns * self.rows)
                      if chars[i] != prev_chars[i] or colors[i] != prev_colors[i]]
        self._previous_checked_chars = chars
        self._previous_checked_colors = colors
        return result

    def setjoystick(self, left=False, right=False, up=False, down=False,
                    leftup=False, rightup=False, leftdown=False, rightdown=False, fire=False):
        self.joy_fire = fire
        self.joy_up = up
        self.joy_down = down
        self.joy_left = left
        self.joy_right = right
        self.joy_leftup = leftup
        self.joy_rightup = rightup
        self.joy_leftdown = leftdown
        self.joy_rightdown = rightdown
        clear_bits = 0   # 0=switch activated...
        if self.joy_up | self.joy_leftup | self.joy_rightup:
            clear_bits |= 1 << 0
        if self.joy_down | self.joy_leftdown | self.joy_rightdown:
            clear_bits |= 1 << 1
        if self.joy_left | self.joy_leftup | self.joy_leftdown:
            clear_bits |= 1 << 2
        if self.joy_right | self.joy_rightup | self.joy_rightdown:
            clear_bits |= 1 << 3
        if self.joy_fire:
            clear_bits |= 1 << 4
        self.memory[56320] = (self.memory[56320] | 0b00011111) & ~clear_bits

    def getjoystick(self):
        # returns left, right, up, down, fire statuses
        j = ~self.memory[56320]  # inverted bits because 0=activated
        return bool(j & 1 << 0), bool(j & 1 << 1), bool(j & 1 << 2), bool(j & 1 << 3), bool(j & 1 << 4)

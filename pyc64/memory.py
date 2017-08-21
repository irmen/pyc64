"""
Commodore-64 Memory representation,
including special functions to handle the (character) screen.

These are integrated because the C-64's screen and colors were
memory-mapped into the memory address space so manipulating bytes of the memory
causes things to happen on the screen immediately.

Written by Irmen de Jong (irmen@razorvine.net)
License: MIT open-source.
"""

import time
import struct
from collections import defaultdict


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
        self.endian = endian     # 'little' or 'big', affects the way 16-bit words are read/written
        self.write_hooks = defaultdict(list)
        self.read_hooks = defaultdict(list)

    def __len__(self):
        return len(self.mem)

    def clear(self):
        """set all memory values to 0."""
        self.mem = bytearray(self.size)

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
                return [self[addr] for addr in range(*addr_or_slice.indices(len(self.mem)))]
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
            self.mem[addr_or_slice] = value
        elif type(addr_or_slice) is slice:
            if any(self.hooked_writes[addr_or_slice]):
                # there's at least one address in the slice with a hook, so... slow mode
                if type(value) is int:
                    for addr in range(*addr_or_slice.indices(len(self.mem))):
                        self[addr] = value
                else:
                    for addr, value in zip(range(*addr_or_slice.indices(len(self.mem))), value):
                        self[addr] = value
            else:
                # there's no address in the slice that's hooked so we can write fast
                if type(value) is int:
                    value = bytes([value]) * len(range(*addr_or_slice.indices(self.size)))
                try:
                    self.mem[addr_or_slice] = value
                except TypeError as x:
                    print(repr(value), x)  # XXX
        else:
            raise TypeError("invalid address type")

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


class ScreenAndMemory:
    colorpalette = (
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

    def __init__(self, columns=40, rows=25, sprites=8):
        # zeropage is from $0000-$00ff
        # screen chars     $0400-$07ff
        # screen colors    $d800-$dbff
        self.memory = Memory(65536)    # 64 Kb
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
            self._full_repaint |= newval & 7 != oldval & 7    # smooth scrolling is done

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
        self.memory[0x000:0x0300] = bytearray(256 * 3)   # clear first 3 pages
        if hard:
            self.memory.clear()
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
        self.memory[0xa000:0xc000] = 96    # basic ROM are all RTS instructions
        self.memory[0xe000:0x10000] = 96     # kernal ROM are all RTS instructions
        self.jiffieclock_epoch = time.perf_counter()
        self.border = 14
        self.screen = 6
        self.text = 14
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
            self.memory[0x0400 + self.cursor] ^= 0x80
            self.memory[0xd800 + self.cursor] = self.text      # @todo preserve char color

    # ASCII-to-PETSCII translation table
    # (non-ascii symbols supported:  £ ↑ ⬆ ← ⬅ ♠ ♥ ♦ ♣ π ● ○ )
    ascii_to_petscii_trans = str.maketrans({
        '\f': 147,  # form feed becomes ClearScreen
        '\n': 13,   # line feed becomes a RETURN
        '\r': 17,   # CR becomes CursorDown
        'a': 65,
        'b': 66,
        'c': 67,
        'd': 68,
        'e': 69,
        'f': 70,
        'g': 71,
        'h': 72,
        'i': 73,
        'j': 74,
        'k': 75,
        'l': 76,
        'm': 77,
        'n': 78,
        'o': 79,
        'p': 80,
        'q': 81,
        'r': 82,
        's': 83,
        't': 84,
        'u': 85,
        'v': 86,
        'w': 87,
        'x': 88,
        'y': 89,
        'z': 90,
        'A': 97,
        'B': 98,
        'C': 99,
        'D': 100,
        'E': 101,
        'F': 102,
        'G': 103,
        'H': 104,
        'I': 105,
        'J': 106,
        'K': 107,
        'L': 108,
        'M': 109,
        'N': 110,
        'O': 111,
        'P': 112,
        'Q': 113,
        'R': 114,
        'S': 115,
        'T': 116,
        'U': 117,
        'V': 118,
        'W': 119,
        'X': 120,
        'Y': 121,
        'Z': 122,
        '{': 179,       # left squiggle
        '}': 235,       # right squiggle
        '£': 92,        # pound currency sign
        '^': 94,        # up arrow
        '~': 126,       # pi math symbol
        'π': 126,       # pi symbol
        '|': 221,       # vertical bar
        '↑': 94,        # up arrow
        '⬆': 94,        # up arrow
        '←': 95,        # left arrow
        '⬅': 95,        # left arrow
        '_': 164,       # lower bar/underscore
        '`': 39,        # single quote
        '♠': 97,        # spades
        '●': 113,       # circle
        '♥': 115,       # hearts
        '○': 119,       # open circle
        '♣': 120,       # clubs
        '♦': 122,       # diamonds
    })

    def writestr(self, txt):
        """Write ASCII text to the screen."""
        # convert ascii to petscii
        self.write(txt.translate(self.ascii_to_petscii_trans))

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

    @classmethod
    def _screen2petscii(cls, screencode):
        """Translate screencode back to PETSCII code"""
        screencode &= 0x7f
        if screencode <= 0x1f:
            return screencode + 64
        if screencode <= 0x3f:
            return screencode
        return screencode + 32

    @classmethod
    def _screen2ascii(cls, screencode):
        """Translate screencode back to ASCII char"""
        return "@abcdefghijklmnopqrstuvwxyz[£]↑← !\"#$%&'()*+,-./0123456789:;<=>?\0ABCDEFGHIJKLMNOPQRSTUVWXYZ" \
               "\0\0|π\0 \0\0\0_\0\0\0\0\0\0}\0\0\0\0\0\0\0{\0\0\0\0\0\0\0\0\0\0\0\0"[screencode & 0x7f]

    def write(self, petscii):
        """Write PETSCII-encoded text to the screen."""
        self._fix_cursor()
        # first, filter out all non-printable chars
        txt = "".join(c for c in petscii if c not in "\x00\x01\x02\x03\x04\x06\x07\x08\x09\x0a\x0b\x0c\x0f\x10\x15\x16"
                      "\x17\x18\x19\x1a\x1b\x80\x82\x83\x84\x85\x86\x87\x88\x89\x8a\x8b\x8c\x8f")
        txt = txt.replace("\x8d", "\x0d")    # replace shift-RETURN by regular RETURN

        def handle_special(c):
            # note: return/shift-return are handled automatically
            txtcolors = {
                '\x05': 1,   # white
                '\x1c': 2,   # red
                '\x1e': 5,   # green
                '\x1f': 6,   # blue
                '\x81': 8,   # orange
                '\x90': 0,   # black
                '\x95': 9,   # brown
                '\x96': 10,  # pink/light red
                '\x97': 11,  # dark grey
                '\x98': 12,  # grey
                '\x99': 13,  # light green
                '\x9a': 14,  # light blue
                '\x9b': 14,  # light grey
                '\x9c': 4,   # purple
                '\x9e': 7,   # yellow
                '\x9f': 3,   # cyan
            }
            if c in txtcolors:
                self.text = txtcolors[c]
            elif c == '\x0d':
                # RETURN, go to next line
                self.cursor = self.columns * (1 + self.cursor // self.columns)
                if self.cursor > self.columns * (self.rows - 1):
                    self._scroll_up()
                    self.cursor = self.columns * (self.rows - 1)
                # also, disable inverse-video
                self.inversevid = False
            elif c == '\x0e':
                self._shifted = True
            elif c == '\x8e':
                self._shifted = False
            elif c == '\x11':
                self.down()
            elif c == '\x91':
                self.up()
            elif c == '\x1d':
                self.right()
            elif c == '\x9d':
                self.left()
            elif c == '\x12':
                self.inversevid = True
            elif c == '\x92':
                self.inversevid = False
            elif c == '\x13':
                self.cursormove(0, 0)   # home
            elif c == '\x14':
                self.backspace()
            elif c == '\x94':
                self.insert()
            elif c == '\x93':
                self.clear()
            else:
                return False
            return True

        prev_cursor_enabled = self._cursor_enabled
        self._cursor_enabled = False
        for c in txt:
            if not handle_special(c):
                self.memory[0x0400 + self.cursor] = self._petscii2screen(ord(c), self.inversevid)
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
            self.memory[0xd800 + self.cursor] = self.text
        if on and not self.cursor_state:
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

    def current_line(self, amount=1, petscii=True, ascii=False):
        if petscii and ascii:
            raise ValueError("select only one result type")
        start = 0x0400 + self.columns * (self.cursor // self.columns)
        self._fix_cursor()
        screencodes = self.memory[start: min(0x0400 + self.columns * self.rows, start + self.columns * amount)]
        self._fix_cursor()
        if petscii:
            return "".join(self._screen2ascii(c) for c in screencodes)
        elif ascii:
            return "".join(chr(self._screen2petscii(c)) for c in screencodes)
        else:
            return "".join(chr(c) for c in screencodes)

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

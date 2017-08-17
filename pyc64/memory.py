"""
Commodore-64 Memory representation,
including special functions to handle the (character) screen.

These are integrated because the C-64's screen and colors were
memory-mapped into the memory address space so manipulating bytes of the memory
causes things to happen on the screen immediately.

Written by Irmen de Jong (irmen@razorvine.net)
License: MIT open-source.
"""

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


class ScreenAndMemory:
    def __init__(self):
        # zeropage is from $0000-$00ff
        # screen chars     $0400-$07ff
        # screen colors    $d800-$dbff
        self._memory = bytearray(65536)    # 64Kb of 'RAM'
        self.reset()

    def reset(self, hard=False):
        self.update_rate = 75
        self._full_repaint = True
        self._shifted = False
        self.inversevid = False
        self.cursor = 0
        self.cursor_state = False
        self.cursor_blink_rate = 300
        self._cursor_enabled = True
        self._previous_checked_chars = bytearray(1000)
        self._previous_checked_colors = bytearray(1000)
        self._memory[0:256] = bytearray(256)   # clear zeropage
        if hard:
            self._memory[0:65536] = bytearray(65536)   # wipe all of the memory
        self.border = 14
        self._screen = 6
        self.text = 14
        self._memory[0xd000:0xd031] = bytearray(0x31)   # wipe VIC registers
        self._memory[0xd027:0xd02f] = [1, 2, 3, 4, 5, 6, 7, 12]    # initial sprite colors
        self.clearscreen()

    @property
    def screen(self):
        return self._screen

    @screen.setter
    def screen(self, color):
        self._screen = color
        self._full_repaint = True

    @property
    def shifted(self):
        return self._shifted

    @shifted.setter
    def shifted(self, boolean):
        self._full_repaint |= boolean != self._shifted
        self._shifted = boolean

    @property
    def cursor_enabled(self):
        return self._cursor_enabled

    @cursor_enabled.setter
    def cursor_enabled(self, enabled):
        if not enabled:
            self._fix_cursor(False)
        self._cursor_enabled = enabled

    def getspritecolors(self):
        return self._memory[0xd027:0xd02f]

    def setspritecolor(self, spritenum, color):
        assert 0 <= spritenum <= 7
        assert 0 <= color <= 255
        self._memory[0xd027 + spritenum] = color

    def getspritepositions(self):
        pos = self._memory[0xd000:0xd010]
        xmsb = self._memory[0xd010]
        return ((pos[i * 2] + (256 if xmsb & 1 << i else 0), pos[1 + i * 2]) for i in range(8))

    def getspritedoubles(self):
        doublex = self._memory[0xd01d]
        doubley = self._memory[0xd017]
        return ((bool(doublex & 1 << i), bool(doubley & 1 << i)) for i in range(8))

    def setspritepos(self, spritenum, x, y):
        assert 0 <= spritenum <= 7
        self._memory[0xd000 + spritenum] = x & 255
        self._memory[0xd001 + spritenum] = y
        if x > 255:
            self._memory[0xd010] |= 1 << spritenum
        else:
            self._memory[0xd010] &= ~ (1 << spritenum)

    def getchar(self, x, y):
        """get the character AND color value at position x,y"""
        assert 0 <= x <= 40 and 0 <= y <= 25, "position out of range"
        offset = x + y * 40
        return self._memory[0x0400 + offset], self._memory[0xd800 + offset]

    def getmem(self, address, word=False):
        # update various special registers:
        assert 0 <= address <= 65535, "invalid address"
        if address == 646:
            self._memory[646] = self.text
        elif address == 53280:
            self._memory[53280] = self.border
        elif address == 53281:
            self._memory[53281] = self._screen
        elif address == 53272:
            self._memory[53272] = 23 if self._shifted else 21
        if word:
            return self._memory[address] + 256 * self._memory[address + 1]
        return self._memory[address]

    def setmem(self, address, value, word=False):
        assert 0 <= address <= 65535, "invalid address"
        if word:
            hi, lo = divmod(value, 256)
            self._memory[address] = lo
            self._memory[address + 1] = hi
        else:
            self._memory[address] = value
        # now trigger various special registers
        if address == 646:
            self.text = value
        elif address == 53280:
            self.border = value
        elif address == 53281:
            self.screen = value
        elif address == 53272:
            self.shifted = bool(value & 2)

    def blink_cursor(self):
        if self.cursor_enabled:
            self.cursor_state = not self.cursor_state
            self._memory[0x0400 + self.cursor] ^= 0x80
            self._memory[0xd800 + self.cursor] = self.text      # @todo preserve char color

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
        '♣': 120,    # clubs
        '♦': 122,    # diamonds
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
                self.cursor = 40 * (1 + self.cursor // 40)
                if self.cursor > 960:
                    self._scroll_up()
                    self.cursor = 960
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
                self.clearscreen()
            else:
                return False
            return True

        prev_cursor_enabled = self._cursor_enabled
        self._cursor_enabled = False
        for c in txt:
            if not handle_special(c):
                self._memory[0x0400 + self.cursor] = self._petscii2screen(ord(c), self.inversevid)
                self._memory[0xd800 + self.cursor] = self.text
                self.cursor += 1
                if self.cursor >= 1000:
                    self._scroll_up()
                    self.cursor = 960
        self._cursor_enabled = prev_cursor_enabled
        self._fix_cursor(True)

    def _fix_cursor(self, on=False):
        if on and not self.cursor_enabled:
            return
        if not on and self.cursor_state:
            self._memory[0x0400 + self.cursor] &= 0x7f
            self._memory[0xd800 + self.cursor] = self.text
        if on and not self.cursor_state:
            self._memory[0x0400 + self.cursor] |= 0x80
            self._memory[0xd800 + self.cursor] = self.text
        self.cursor_state = on

    def _scroll_up(self, fill=(32, None)):
        # scroll the screen up one line
        self._memory[0x0400: 0x0400 + 960] = self._memory[0x0400 + 40: 0x0400 + 1000]
        self._memory[0xd800: 0xd800 + 960] = self._memory[0xd800 + 40: 0xd800 + 1000]
        fillchar = fill[0]
        fillcolor = self.text if fill[1] is None else fill[1]
        self._memory[0x0400 + 960: 0x0400 + 1000] = [fillchar] * 40
        self._memory[0xd800 + 960: 0xd800 + 1000] = [fillcolor] * 40

    def _scroll_down(self, fill=(32, None)):
        # scroll the screen down one line
        self._memory[0x0400 + 40: 0x0400 + 1000] = self._memory[0x0400: 0x0400 + 960]
        self._memory[0xd800 + 40: 0xd800 + 1000] = self._memory[0xd800: 0xd800 + 960]
        fillchar = fill[0]
        fillcolor = self.text if fill[1] is None else fill[1]
        self._memory[0x0400: 0x0400 + 40] = [fillchar] * 40
        self._memory[0xd800: 0xd800 + 40] = [fillcolor] * 40

    def _scroll_left(self, fill=(32, None)):
        # scroll the screen left one colum
        fillchar = fill[0]
        fillcolor = self.text if fill[1] is None else fill[1]
        for y in range(0, 1000, 40):
            self._memory[0x0400 + y: 0x0400 + y + 39] = self._memory[0x0400 + y + 1: 0x0400 + y + 40]
            self._memory[0xd800 + y: 0xd800 + y + 39] = self._memory[0xd800 + y + 1: 0xd800 + y + 40]
        self._memory[0x0400 + 39: 0x0400 + 1000: 40] = [fillchar] * 25
        self._memory[0xd800 + 39: 0xd800 + 1000: 40] = [fillcolor] * 25

    def _scroll_right(self, fill=(32, None)):
        # scroll the screen right one colum
        fillchar = fill[0]
        fillcolor = self.text if fill[1] is None else fill[1]
        for y in range(0, 1000, 40):
            self._memory[0x0400 + y + 1:0x0400 + y + 40] = self._memory[0x0400 + y:0x0400 + y + 39]
            self._memory[0xd800 + y + 1:0xd800 + y + 40] = self._memory[0xd800 + y:0xd800 + y + 39]
        self._memory[0x0400:0x0400 + 1000:40] = [fillchar] * 25
        self._memory[0xd800:0xd800 + 1000:40] = [fillcolor] * 25

    def scroll(self, up=False, down=False, left=False, right=False, fill=(32, None)):
        self._fix_cursor()
        if up:
            self._scroll_up(fill)
        if down:
            self._scroll_down(fill)
        if left:
            self._scroll_left(fill)
        if right:
            self._scroll_right(fill)
        self._fix_cursor(True)

    def return_key(self):
        self._fix_cursor()
        self.cursor = 40 * (self.cursor // 40) + 40
        if self.cursor >= 1000:
            self._scroll_up()
            self.cursor -= 40
        self._fix_cursor(on=True)

    def backspace(self):
        if self.cursor > 0:
            self._fix_cursor()
            self.cursor -= 1
            end = 40 * (self.cursor // 40) + 39
            self._memory[0x0400 + self.cursor: 0x0400 + end] = self._memory[0x0400 + self.cursor + 1: 0x0400 + end + 1]
            self._memory[0xd800 + self.cursor: 0xd800 + end] = self._memory[0xd800 + self.cursor + 1: 0xd800 + end + 1]
            self._memory[0x0400 + end] = 32
            self._memory[0xd800 + end] = self.text
            self._fix_cursor(on=True)

    def insert(self):
        if self.cursor < 999:
            self._fix_cursor()
            end = 40 * (self.cursor // 40) + 40
            self._memory[0x0400 + self.cursor + 1: 0x0400 + end] = self._memory[0x0400 + self.cursor: 0x0400 + end - 1]
            self._memory[0xd800 + self.cursor + 1: 0xd800 + end] = self._memory[0xd800 + self.cursor: 0xd800 + end - 1]
            self._memory[0x0400 + self.cursor] = 32
            self._memory[0xd800 + self.cursor] = self.text
            self._fix_cursor(on=True)

    def up(self):
        self._fix_cursor()
        if self.cursor < 40:
            self._scroll_down()
        else:
            self.cursor -= 40
        self._fix_cursor(on=True)

    def down(self):
        self._fix_cursor()
        if self.cursor >= 960:
            self._scroll_up()
        else:
            self.cursor += 40
        self._fix_cursor(on=True)

    def left(self):
        if self.cursor > 0:
            self._fix_cursor()
            self.cursor -= 1
            self._fix_cursor(on=True)

    def right(self):
        if self.cursor < 1000:
            self._fix_cursor()
            self.cursor += 1
            self._fix_cursor(on=True)

    def clearscreen(self):
        self._memory[0x0400: 0x0400 + 1000] = [32] * 1000
        self._memory[0xd800: 0xd800 + 1000] = [self.text] * 1000
        self.cursor = 0
        self._fix_cursor(on=True)

    def cursormove(self, x, y):
        self._fix_cursor()
        self.cursor = x + 40 * y
        self._fix_cursor(on=True)

    def cursorpos(self):
        row, col = divmod(self.cursor, 40)
        return col, row

    def current_line(self, amount=1, petscii=True, ascii=False):
        if petscii and ascii:
            raise ValueError("select only one result type")
        start = 0x0400 + 40 * (self.cursor // 40)
        self._fix_cursor()
        screencodes = self._memory[start:min(0x07e8, start + 40 * amount)]
        self._fix_cursor()
        if petscii:
            return "".join(self._screen2ascii(c) for c in screencodes)
        elif ascii:
            return "".join(chr(self._screen2petscii(c)) for c in screencodes)
        else:
            return "".join(chr(c) for c in screencodes)

    @classmethod
    def test_screencode_mappings(cls):
        for c in range(32, 128):
            sc = cls._petscii2screen(c)
            cc = cls._screen2petscii(sc)
            if cc != c:
                print("char mapping error: %d -> %d -> %d" % (c, sc, cc))

    def getdirty(self):
        if self._full_repaint:
            self._full_repaint = False
            result = [(i, (self._memory[0x0400 + i], self._memory[0xd800 + i])) for i in range(1000)]
        else:
            result = [(i, (self._memory[0x0400 + i], self._memory[0xd800 + i]))
                      for i in range(1000)
                      if self._memory[0x0400 + i] != self._previous_checked_chars[i] or
                      self._memory[0xd800 + i] != self._previous_checked_colors[i]]
        if result:
            self._previous_checked_chars = self._memory[0x0400:0x07e8]
            self._previous_checked_colors = self._memory[0xd800:0xdbe8]
        return result

    def getscreencopy(self):
        return self._memory[0x0400:0x07e8], self._memory[0xd800:0xdbe8]

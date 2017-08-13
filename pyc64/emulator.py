import re
import os
import tkinter
from PIL import Image


class C64Screen:
    palette = (
        0x000000,  # black
        0xFFFFFF,  # white
        0x68372B,  # red
        0x70A4B2,  # cyan
        0x6F3D86,  # purple
        0x588D43,  # green
        0x352879,  # blue
        0xB8C76F,  # yellow
        0x6F4F25,  # orange
        0x433900,  # brown
        0x9A6759,  # ligth red
        0x444444,  # dark grey
        0x6C6C6C,  # medium grey
        0x9AD284,  # light green
        0x6C5EB5,  # light blue
        0x959595,  # light grey
    )

    # special non-ascii symbols supported:  £ ↑ ⬆ ← ⬅ ♠ ♥ ♦ ♣ π ● ○
    str_to_64_trans = str.maketrans({
        '@': 0,
        'a': 1,
        'b': 2,
        'c': 3,
        'd': 4,
        'e': 5,
        'f': 6,
        'g': 7,
        'h': 8,
        'i': 9,
        'j': 10,
        'k': 11,
        'l': 12,
        'm': 13,
        'n': 14,
        'o': 15,
        'p': 16,
        'q': 17,
        'r': 18,
        's': 19,
        't': 20,
        'u': 21,
        'v': 22,
        'w': 23,
        'x': 24,
        'y': 25,
        'z': 26,
        '[': 27,
        '\\': 28,
        '£': 28,        # pound currency sign
        ']': 29,
        '~': 30,        # up arrow
        '↑': 30,        # up arrow
        '⬆': 30,        # up arrow
        '_': 31,        # left arrow
        '←': 31,        # left arrow
        '⬅': 31,        # left arrow
        ' ': 32,
        '!': 33,
        '"': 34,
        '#': 35,
        '$': 36,
        '%': 37,
        '&': 38,
        '`': 39,
        '\'': 39,
        '(': 40,
        ')': 41,
        '*': 42,
        '+': 43,
        ',': 44,
        '-': 45,
        '.': 46,
        '/': 47,
        '0': 48,
        '1': 49,
        '2': 50,
        '3': 51,
        '4': 52,
        '5': 53,
        '6': 54,
        '7': 55,
        '8': 56,
        '9': 57,
        ':': 58,
        ';': 59,
        '<': 60,
        '=': 61,
        '>': 62,
        '?': 63,
        '♠': 65,    # spades
        '●': 81,    # circle
        '♥': 83,    # hearts
        '○': 87,    # open circle
        '♣': 88,    # clubs
        '♦': 90,    # diamonds
        'π': 94,    # pi symbol
    })

    c64_to_str_trans_normal = {v: k for k, v in str_to_64_trans.items()}
    c64_to_str_trans_shifted = {v: k for k, v in str_to_64_trans.items()}
    for c in range(ord('A'), ord('Z')+1):
        c64_to_str_trans_shifted[c] = chr(c)

    def __init__(self):
        self.border = 0
        self.screen = 0
        self.text = 0
        self.shifted = False
        self.cursor = 0
        self.cursor_state = False
        self.cursor_blink_rate = 300
        self.chars = [32]*40*25      # $0400-$07ff
        self.colors = [self.text] * 40 * 25    # $d800-$dbff
        self.reset()

    def reset(self):
        self.border = 14
        self.screen = 6
        self.text = 14
        self.shifted = False
        self.cursor = 0
        self.cursor_state = False
        self.cursor_blink_rate = 300
        for i in range(1000):
            self.chars[i] = 32
            self.colors[i] = self.text
        self.writestr("\n    **** commodore 64 basic v2 ****\n")
        self.writestr("\n 64k ram system  38911 basic bytes free\n")
        self.writestr("\nready.\n")

    def blink_cursor(self):
        self.cursor_state = not self.cursor_state
        self.chars[self.cursor] ^= 0x80
        self.colors[self.cursor] = self.text

    @classmethod
    def str2screen(cls, string):
        """
        Convert ascii string to C64 screencodes.
        A few non-ascii symbols are also supported:  £ ↑ ⬆ ← ⬅ ♠ ♥ ♦ ♣ π ● ○
        NOTE: Text should be given in lowercase. Uppercase text will output PETSCII symbols.
        """
        return string.translate(cls.str_to_64_trans)

    def writestr(self, txt, petscii=False):
        self._fix_cursor()
        cursor = self.cursor
        lines = txt.split("\n")
        first_line = True
        for line in lines:
            if not first_line:
                cursor = 40 * (cursor // 40) + 40
                if cursor >= 1000:
                    self._scroll_up()
                    cursor -= 40
            first_line = False
            if not petscii:
                line = self.str2screen(line)
            for c in line:
                self.chars[cursor] = ord(c)
                self.colors[cursor] = self.text
                cursor += 1
                if cursor >= 1000:
                    self._scroll_up()
                    cursor -= 40
        self.cursor = cursor
        self._fix_cursor(on=True)

    def _fix_cursor(self, on=False):
        if on:
            self.cursor_state = True
        if self.cursor_state:
            self.chars[self.cursor] ^= 0x80
            self.colors[self.cursor] = self.text

    def _scroll_up(self):
        # scroll the screen up one line
        for i in range(0, 960):
            self.chars[i] = self.chars[i + 40]
            self.colors[i] = self.colors[i + 40]
        for i in range(960, 1000):
            self.chars[i] = 32
            self.colors[i] = self.text

    def _scroll_down(self):
        # scroll the screen down one line
        for i in range(999, 39, -1):
            self.chars[i] = self.chars[i - 40]
            self.colors[i] = self.colors[i - 40]
        for i in range(0, 40):
            self.chars[i] = 32
            self.colors[i] = self.text

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
            self.chars[self.cursor] = 32
            self.colors[self.cursor] = self.text
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
        for i in range(1000):
            self.chars[i] = 32
            self.colors[i] = self.text
        self.cursor = 0
        self._fix_cursor(on=True)

    def cursorhome(self):
        self._fix_cursor()
        self.cursor = 0
        self._fix_cursor(on=True)

    def insert(self):
        self._fix_cursor()
        for i in range(40*(self.cursor // 40) + 39, self.cursor, -1):
            self.chars[i] = self.chars[i-1]
            self.colors[i] = self.colors[i-1]
        self.chars[self.cursor] = 32
        self.colors[self.cursor] = self.text
        self._fix_cursor(on=True)

    def current_line(self):
        start = 40 * (self.cursor // 40)
        self._fix_cursor()
        chars = [chr(c) for c in self.chars[start:start+40]]
        self._fix_cursor()
        trans = self.c64_to_str_trans_shifted if self.shifted else self.c64_to_str_trans_normal
        return ("".join(chars)).translate(trans)


class BasicError(Exception):
    pass


class BasicInterpreter:
    def __init__(self, screen):
        self.screen = screen
        import math, hashlib, base64, binascii, sys, platform, Pyro4
        self.symbols = {
            "md5": hashlib.md5,
            "sha256": hashlib.sha256,
            "sha512": hashlib.sha512,
            "b64decode": base64.b64decode,
            "b64encode": base64.b64encode,
            "crc32": binascii.crc32,
            "os" : os,
            "sys": sys,
            "platform": platform,
            "π": math.pi,
            "pyro4": Pyro4
        }
        for x in dir(math):
            if '_' not in x:
                self.symbols[x] = getattr(math, x)

    def execute_line(self, line):
        try:
            parts = [x for x in (p.strip() for p in line.split(":")) if x]
            print("RUN CMDS:", parts)  # XXX
            if parts:
                for cmd in parts:
                    self._execute_cmd(cmd)
                self.screen.writestr("\nready.\n")
        except BasicError as bx:
            self.screen.writestr("\n?" + bx.args[0] + "  error\nready.\n")
        except Exception as ex:
            self.screen.writestr("\n?" + str(ex).lower() + "  error\nready.\n")

    def _execute_cmd(self, cmd):
        if cmd.startswith("read") or cmd.startswith("rE"):
            raise BasicError("out of data")
        elif cmd.startswith("load") or cmd.startswith("lO"):
            raise BasicError("file not found")
        elif cmd.startswith("print") or cmd.startswith("?"):
            self.execute_print(cmd)
        elif cmd.startswith("poke") or cmd.startswith("pO"):
            self.execute_poke(cmd)
        else:
            match = re.match(r"([a-zA-Z]+[0-9]*)\s*=\s*(\S+)$", cmd)
            if match:
                symbol, value = match.groups()
                self.symbols[symbol] = eval(value, self.symbols)
            else:
                raise BasicError("syntax")

    def execute_print(self, cmd):
        if cmd.startswith("?"):
            cmd = cmd[1:]
        elif cmd.startswith("print"):
            cmd = cmd[5:]
        if cmd:
            result = str(eval(cmd, self.symbols))
        else:
            result = ""
        self.screen.writestr(" " + result + "\n")

    def execute_poke(self, cmd):
        if cmd.startswith("pO"):
            cmd = cmd[2:]
        elif cmd.startswith("poke"):
            cmd = cmd[5:]
        addr, value = cmd.split(",")
        addr, value = eval(addr, self.symbols), eval(value, self.symbols)
        if addr == 646:
            self.screen.text = value
        elif addr == 53280:
            self.screen.border = value
        elif addr == 53281:
            self.screen.screen = value
        elif 0x0400 <= addr <= 0x07e7:
            self.screen.chars[addr - 0x0400] = value
        elif 0xd800 <= addr <= 0xdbe7:
            self.screen.colors[addr - 0xd800] = value
        elif addr == 53265:
            raise BasicError("screenmode switch not possible")


class EmulatorWindow(tkinter.Tk):
    def __init__(self, title):
        super().__init__()
        self.dirprefix = os.path.dirname(__file__)
        self.wm_title(title)
        self.geometry("+200+100")
        self.screen = C64Screen()
        self.basic = BasicInterpreter(self.screen)
        self.canvas = tkinter.Canvas(self, width=128+40*16, height=128+25*16, borderwidth=0, highlightthickness=0)
        topleft = self.screencor((0, 0))
        botright = self.screencor((40, 25))
        self.screenrect = self.canvas.create_rectangle(topleft[0], topleft[1], botright[0], botright[1], outline="")
        self.create_charsets()
        # create the 1000 character bitmaps fixed on the canvas:
        self.charbitmaps = []
        for y in range(25):
            for x in range(40):
                cor = self.screencor((x, y))
                bm = self.canvas.create_bitmap(cor[0], cor[1], bitmap="@"+os.path.join(self.dirprefix, "charset/normal-20.xbm"),
                                               foreground="black", background="white", anchor=tkinter.NW, tags="charbitmap")
                self.charbitmaps.append(bm)
        self.key_shift_down = False
        self.key_control_down = False
        self.bind("<KeyPress>", lambda event: self.keypress(*self._keyevent(event)))
        self.bind("<KeyRelease>", lambda event: self.keyrelease(*self._keyevent(event)))
        self.repaint()
        self.canvas.pack()
        self.after(self.screen.cursor_blink_rate, self.blink_cursor)

    def _keyevent(self, event):
        c = event.char
        if not c or ord(c) > 255:
            c = event.keysym
        return c, (event.x, event.y)

    def keypress(self, char, mouseposition):
        # print("keypress", repr(char), mouseposition)
        if char.startswith("Shift"):
            self.key_shift_down = True
        if char.startswith("Control"):
            self.key_control_down = True

        if char.startswith(("Shift", "Control")):
            if self.key_shift_down and self.key_control_down:
                self.screen.shifted = not self.screen.shifted

        if len(char) == 1:
            # if '1' <= char <= '8' and self.key_control_down:
            #     self.c64screen.text = ord(char)-1
            if char == '\r':
                line = self.screen.current_line()
                self.screen.return_key()
                self.basic.execute_line(line)
            elif char == '\x7f':
                if self.key_shift_down:
                    self.screen.insert()
                else:
                    self.screen.backspace()
            elif char == '\x08':
                self.screen.backspace()
            elif char == '\x1b':
                self.runstop()
            elif '\x01' <= char <= '\x1a':
                # @todo fix key-to-petscii mapping
                self.screen.writestr(chr(ord(char) + 111), petscii=True)   # simulate commodore key for PETSCII symbols
            else:
                self.screen.writestr(char)
            self.repaint()
        else:
            # some control character
            if char == "Up":
                self.screen.up()
                self.repaint()
            elif char == "Down":
                self.screen.down()
                self.repaint()
            elif char == "Left":
                self.screen.left()
                self.repaint()
            elif char == "Right":
                self.screen.right()
                self.repaint()
            elif char == 'Home':
                if self.key_shift_down:
                    self.screen.clearscreen()
                else:
                    self.screen.cursorhome()
                self.repaint()
            elif char == 'Insert':
                self.screen.insert()
                self.repaint()

    def runstop(self):
        print("runstop")

    def keyrelease(self, char, mouseposition):
        # print("keyrelease", repr(char), mouseposition)
        if char.startswith("Shift"):
            self.key_shift_down = False
        if char.startswith("Control"):
            self.key_control_down = False

    def create_charsets(self):
        # normal
        source_chars = Image.open(os.path.join(self.dirprefix, "charset-normal.png"))
        for i in range(256):
            chars = source_chars.copy()
            row, col = divmod(i, 40)
            ci = chars.crop((col*16, row*16, col*16+16, row*16+16))
            ci = ci.convert(mode="1", dither=None)
            ci.save(os.path.join(self.dirprefix, "charset/normal-{:02x}.xbm".format(i)), "xbm")
        # shifted
        source_chars = Image.open(os.path.join(self.dirprefix, "charset-shifted.png"))
        for i in range(256):
            chars = source_chars.copy()
            row, col = divmod(i, 40)
            ci = chars.crop((col*16, row*16, col*16+16, row*16+16))
            ci = ci.convert(mode="1", dither=None)
            ci.save(os.path.join(self.dirprefix, "charset/shifted-{:02x}.xbm".format(i)), "xbm")

    def repaint(self):
        # set border color and screen color
        self.canvas["bg"] = self.tkcolor(self.screen.border)
        self.canvas.itemconfigure(self.screenrect, fill=self.tkcolor(self.screen.screen))
        bgcol = self.tkcolor(self.screen.screen)
        for y in range(25):
            for x in range(40):
                forecol = self.tkcolor(self.screen.colors[x + y * 40])
                bm = self.charbitmaps[x+y*40]
                style = "shifted" if self.screen.shifted else "normal"
                bitmap = "@"+os.path.join(self.dirprefix, "charset/{:s}-{:02x}.xbm".format(style, self.screen.chars[x + y * 40]))
                self.canvas.itemconfigure(bm, foreground=forecol, background=bgcol, bitmap=bitmap)

    def screencor(self, cc):
        return 64+cc[0]*16, 64+cc[1]*16

    def tkcolor(self, color):
        return "#{:06x}".format(C64Screen.palette[color % 16])

    def blink_cursor(self):
        self.screen.blink_cursor()
        self.repaint()
        self.after(self.screen.cursor_blink_rate, self.blink_cursor)


def setup():
    emu = EmulatorWindow("s1")
    emu.mainloop()


if __name__=="__main__":
    setup()

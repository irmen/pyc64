"""
'fast' Commodore-64 'emulator' in 100% pure Python 3.x :)

Note: the basic dialect is woefully incomplete and the commands that
are provided are often not even compatible with their originals on the C64,
but they do try to support *some* of the BASIC 2.0 structure.

The most important thing that is missing is the ability to
to do any 'blocking' operation such as INPUT or WAIT.
Creating an interactive program is not possible at this point.
The SLEEP command is added only as a hack, to be able to at least
slow down the thing at certain points.

Written by Irmen de Jong (irmen@razorvine.net)
License: MIT open-source.

"""
import sys
import re
import os
import array
import tkinter
import traceback
import numbers
import glob
import time
from PIL import Image


class ScreenAndMemory:
    palette = (
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

    def __init__(self):
        self.border = 0
        self._screen = 0
        self.text = 0
        self._shifted = False
        self.inversevid = False
        self.cursor = 0
        self.cursor_state = False
        self.cursor_blink_rate = 300
        self._cursor_enabled = True
        self._full_repaint = True
        self.update_rate = 100
        # zeropage is from $0000-$00ff
        # screen chars     $0400-$07ff
        # screen colors    $d800-$dbff
        self._memory = array.array('B', [0] * 65536)    # 64Kb of 'RAM'
        self.reset()

    def reset(self, hard=False):
        self.border = 14
        self._screen = 6
        self._full_repaint = True
        self.text = 14
        self._shifted = False
        self.inversevid = False
        self.cursor = 0
        self.cursor_state = False
        self.cursor_blink_rate = 300
        self.cursor_enabled = True
        self._previous_checked_chars = array.array('B', [0] * 1000)
        self._previous_checked_colors = array.array('B', [0] * 1000)
        for i in range(256):
            self._memory[i] = 0
        if hard:
            # wipe all of the memory
            for i in range(256, 65536):
                self._memory[i] = 0
        for i in range(1000):
            self._memory[0x0400 + i] = 32
            self._memory[0xd800 + i] = self.text

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
            self._fix_cursor()
        self._cursor_enabled = enabled

    def getchar(self, x, y):
        """get the character AND color value at position x,y"""
        offset = x + y * 40
        return self._memory[0x0400 + offset], self._memory[0xd800 + offset]

    def getmem(self, address, word=False):
        # update various special registers:
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

    def setmem(self, addr, value, word=False):
        if word:
            hi, lo = divmod(value, 256)
            self._memory[addr] = lo
            self._memory[addr + 1] = hi
        else:
            self._memory[addr] = value
        # now trigger various special registers
        if addr == 646:
            self.text = value
        elif addr == 53280:
            self.border = value
        elif addr == 53281:
            self.screen = value
        elif addr == 53272:
            self.shifted = bool(value & 2)

    def blink_cursor(self):
        self.cursor_state = not self.cursor_state
        self._memory[0x0400 + self.cursor] ^= 0x80
        self._memory[0xd800 + self.cursor] = self.text

    # ASCII-to-PETSCII translation table
    # (non-ascii symbols supported:  £ ↑ ⬆ ← ⬅ ♠ ♥ ♦ ♣ π ● ○ )
    ascii_to_petscii_trans = str.maketrans({
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
        lines = txt.split("\x0d")    # line breaks are not the lF but the RETURN char ('\r')
        first_line = True

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
        for line in lines:
            if not first_line:
                self.cursor = 40 * (self.cursor // 40 + 1)
                if self.cursor >= 960:
                    self._scroll_up()
                    self.cursor = 960
            first_line = False
            for c in line:
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
        if on:
            self.cursor_state = True
        if self.cursor_state & self._cursor_enabled:
            self._memory[0x0400 + self.cursor] ^= 0x80
            self._memory[0xd800 + self.cursor] = self.text

    def _scroll_up(self):
        # scroll the screen up one line
        for i in range(0, 960):
            self._memory[0x0400 + i] = self._memory[0x0400 + 40 + i]
            self._memory[0xd800 + i] = self._memory[0xd800 + 40 + i]
        for i in range(960, 1000):
            self._memory[0x0400 + i] = 32
            self._memory[0xd800 + i] = self.text

    def _scroll_down(self):
        # scroll the screen down one line
        for i in range(999, 39, -1):
            self._memory[0x0400 + i] = self._memory[0x0400 - 40 + i]
            self._memory[0xd800 + i] = self._memory[0xd800 - 40 + i]
        for i in range(0, 40):
            self._memory[0x0400 + i] = 32
            self._memory[0xd800 + i] = self.text

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
        for i in range(1000):
            self._memory[0x400 + i] = 32
            self._memory[0xd800 + i] = self.text
        self.cursor = 0
        self._fix_cursor(on=True)

    def cursormove(self, x, y):
        self._fix_cursor()
        self.cursor = x + 40 * y
        self._fix_cursor(on=True)

    def cursorpos(self):
        row, col = divmod(self.cursor, 40)
        return col, row

    def insert(self):
        self._fix_cursor()
        for i in range(40 * (self.cursor // 40) + 39, self.cursor, -1):
            self._memory[0x0400 + i] = self._memory[0x0400 - 1 + i]
            self._memory[0xd800 + i] = self._memory[0xd800 - 1 + i]
        self._memory[0x0400 + self.cursor] = 32
        self._memory[0xd800 + self.cursor] = self.text
        self._fix_cursor(on=True)

    def current_line(self, amount=1, petscii=True, ascii=False):
        if petscii and ascii:
            raise ValueError("select only one result type")
        start = 0x0400 + 40 * (self.cursor // 40)
        self._fix_cursor()
        screencodes = self._memory[start:start + 40 * amount]
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
                      if self._memory[0x0400 + i] != self._previous_checked_chars[i]
                      or self._memory[0xd800 + i] != self._previous_checked_colors[i]]
        if result:
            self._previous_checked_chars = self._memory[0x0400:0x07e8]
            self._previous_checked_colors = self._memory[0xd800:0xdbe8]
        return result

    def getscreencopy(self):
        return self._memory[0x0400:0x07e8], self._memory[0xd800:0xdbe8]


class BasicError(Exception):
    pass


class FlowcontrolException(Exception):
    pass


class ResetMachineError(FlowcontrolException):
    pass


class StartRunloop(FlowcontrolException):
    pass


class GotoLine(FlowcontrolException):
    def __init__(self, line):
        self.line = line


class SleepTimer(FlowcontrolException):
    def __init__(self, duration):
        self.duration = duration


class StopRunloop(FlowcontrolException):
    pass


class BasicInterpreter:
    def __init__(self, screen):
        self.screen = screen
        self.program = {}
        self.reset()

    def reset(self):
        import math, hashlib, base64, binascii, sys, platform, random
        self.symbols = {
            "md5": hashlib.md5,
            "sha256": hashlib.sha256,
            "sha512": hashlib.sha512,
            "b64decode": base64.b64decode,
            "b64encode": base64.b64encode,
            "crc32": binascii.crc32,
            "os": os,
            "sys": sys,
            "platform": platform,
            "π": math.pi,
            "peek": self.peek_func,
            "pE": self.peek_func,
            "wpeek": self.wpeek_func,
            "wpE": self.wpeek_func,
            "rnd": lambda *args: random.random(),
            "rndi": random.randrange,
            "asc": ord
        }
        for x in dir(math):
            if '_' not in x:
                self.symbols[x] = getattr(math, x)
        self.program = {}
        self.forloops = {}
        self.data_line = None
        self.data_index = None
        self.cont_line_index = self.current_run_line_index = None
        self.program_lines = None
        self.last_run_error = None
        self.screen.writestr("\r    **** commodore 64 basic v2 ****\r")
        self.screen.writestr("\r 64k ram system  38911 basic bytes free\r")
        self.screen.writestr("\rready.\r")
        self.stop_run()

    def execute_line(self, line, print_ready=True):
        try:
            # if there's no char on the last pos of the first line, only evaluate the first line
            if len(line) >= 40 and line[39] == ' ':
                line = line[:40]
            if self.process_programline_entry(line):
                return
            if line.startswith(("#", "rem")):
                return
            if line.startswith("data"):
                # data is only consumed with a read statement
                return
            parts = [x for x in (p.strip() for p in line.split(":")) if x]
            self.last_run_error = None
            if parts:
                for cmd in parts:
                    do_more = self._execute_cmd(cmd, parts)
                    if not do_more:
                        break
                if self.current_run_line_index is None and print_ready:
                    self.screen.writestr("\rready.\r")
        except FlowcontrolException:
            raise
        except BasicError as bx:
            if self.current_run_line_index is None:
                self.screen.writestr("\r?" + bx.args[0].lower() + "  error\rready.\r")
            else:
                self.last_run_error = bx.args[0].lower()
                line = self.program_lines[self.current_run_line_index]
                self.screen.writestr("\r?" + bx.args[0].lower() + "  error in {line:d}\rready.\r".format(line=line))
            traceback.print_exc()
        except Exception as ex:
            if self.current_run_line_index is not None:
                self.last_run_error = str(ex).lower()
            self.screen.writestr("\r?" + str(ex).lower() + "  error\rready.\r")
            traceback.print_exc()

    def process_programline_entry(self, line):
        match = re.match("(\d+)(\s*.*)", line)
        if match:
            if self.current_run_line_index is not None:
                raise BasicError("cannot define lines while running")
            linenum, line = match.groups()
            line = line.strip()
            linenum = int(linenum)
            if not line:
                if linenum in self.program:
                    del self.program[linenum]
            else:
                self.program[linenum] = line
            return True
        return False

    def _execute_cmd(self, cmd, all_cmds_on_line=None):
        # print("RUN CMD:", repr(cmd))
        if cmd.startswith(("read", "rE")):
            self.execute_read(cmd)
        elif cmd.startswith(("restore", "reS")):
            self.execute_restore(cmd)
        elif cmd.startswith(("save", "sA")):
            self.execute_save(cmd)
            return False
        elif cmd.startswith(("load", "lO")):
            self.execute_load(cmd)
            return False
        elif cmd.startswith(("print", "?")):
            self.execute_print(cmd)
        elif cmd.startswith(("poke", "pO")):
            self.execute_poke(cmd)
        elif cmd.startswith(("wpoke", "wpO")):
            self.execute_wpoke(cmd)
        elif cmd.startswith(("list", "lI")):
            self.execute_list(cmd)
            return False
        elif cmd.startswith(("new", "nI")):
            self.execute_new(cmd)
            return False
        elif cmd.startswith(("run", "rU")):
            self.execute_run(cmd)
            return False
        elif cmd.startswith(("sys", "sY")):
            self.execute_sys(cmd)
        elif cmd.startswith(("goto", "gO")):
            self.execute_goto(cmd)
        elif cmd.startswith(("for", "fO")):
            self.execute_for(cmd, all_cmds_on_line)
        elif cmd.startswith(("next", "nE")):
            self.execute_next(cmd)
        elif cmd.startswith("if"):
            self.execute_if(cmd)
        elif cmd.startswith(("#", "rem")):
            pass
        elif cmd.startswith(("end", "eN")):
            self.execute_end(cmd)
            return False
        elif cmd.startswith(("stop", "sT")):
            self.execute_end(cmd)
            return False
        elif cmd.startswith(("cont", "cO")):
            self.execute_cont(cmd)
        elif cmd.startswith(("sleep", "sL")):
            self.execute_sleep(cmd)
        elif cmd == "cls":
            self.screen.clearscreen()
        elif cmd.startswith("dos\""):
            self.execute_dos(cmd)
            return False
        else:
            match = re.match(r"([a-zA-Z]+[0-9]*)\s*=\s*(\S+)$", cmd)
            if match:
                # variable assignment
                symbol, value = match.groups()
                self.symbols[symbol] = eval(value, self.symbols)
                return True
            else:
                raise BasicError("syntax")
        return True

    def execute_print(self, cmd):
        if cmd.startswith("?"):
            cmd = cmd[1:]
        elif cmd.startswith("print"):
            cmd = cmd[5:]
        print_return = "\r"
        if cmd:
            if cmd.endswith((',', ';')):
                cmd = cmd[:-1]
                print_return = ""
            result = eval(cmd, self.symbols)
            if isinstance(result, numbers.Number):
                if result < 0:
                    result = str(result) + " "
                else:
                    result = " " + str(result) + " "
            else:
                result = str(result)
        else:
            result = ""
        self.screen.writestr(result + print_return)

    def execute_for(self, cmd, all_cmds_on_line=None):
        if cmd.startswith("fO"):
            cmd = cmd[2:]
        elif cmd.startswith("for"):
            cmd = cmd[3:]
        cmd = cmd.strip()
        match = re.match("(\w+)\s*=\s*(\S+)\s*to\s*(\S+)\s*(?:step\s*(\S+))?$", cmd)
        if match:
            if self.current_run_line_index is None:
                raise BasicError("illegal direct")    # we only support for loops in a program (with line numbers), not on the screen
            if all_cmds_on_line and len(all_cmds_on_line) > 1:
                raise BasicError("for not alone on line")    # we only can loop to for statements that are alone on their own line
            varname, start, to, step = match.groups()
            if step is None:
                step = "1"
            start = eval(start, self.symbols)
            to = eval(to, self.symbols)
            step = eval(step, self.symbols)
            iterator = iter(range(start, to + 1, step))
            self.forloops[varname] = (self.current_run_line_index, iterator)
            self.symbols[varname] = next(iterator)
        else:
            raise BasicError("syntax")

    def execute_next(self, cmd):
        if cmd.startswith("nE"):
            cmd = cmd[2:]
        elif cmd.startswith("next"):
            cmd = cmd[4:]
        varname = cmd.strip()
        if self.current_run_line_index is None:
            raise BasicError("illegal direct")  # we only support for loops in a program (with line numbers), not on the screen
        if not varname:
            raise BasicError("next without varname")    # we require the varname for now
        if varname not in self.forloops or varname not in self.symbols:
            raise BasicError("next without for")
        if "," in varname:
            raise BasicError("next with multiple vars")    # we only support one var right now
        try:
            runline_index, iterator = self.forloops[varname]
            self.symbols[varname] = next(iterator)
        except StopIteration:
            del self.forloops[varname]
        else:
            self.current_run_line_index = runline_index   # jump back to code at line after for loop

    def execute_goto(self, cmd):
        if cmd.startswith("gO"):
            cmd = cmd[2:]
        elif cmd.startswith("goto"):
            cmd = cmd[4:]
        line = int(cmd)
        if self.current_run_line_index is None:
            # do a run instead
            self.execute_run("run " + str(line))
        else:
            if line not in self.program:
                raise BasicError("undef'd statement")
            raise GotoLine(line)

    def execute_sleep(self, cmd):
        if cmd.startswith("sL"):
            cmd = cmd[2:]
        elif cmd.startswith("sleep"):
            cmd = cmd[5:]
        howlong = float(cmd)
        raise SleepTimer(howlong)

    def execute_end(self, cmd):
        if cmd not in ("eN", "end", "sT", "stop"):
            raise BasicError("syntax")
        if self.current_run_line_index is not None:
            if cmd in ("sT", "stop"):
                self.screen.writestr("\rbreak in {:d}\r".format(self.program_lines[self.current_run_line_index]))
            self.stop_run()
            raise StopRunloop()

    def execute_cont(self, cmd):
        # Only works on a per-line basis!
        # so if program breaks in the middle of a line and you CONT it,
        # it will just resume with the line following it. This can result in parts of code being skipped.
        # Solving this is complex it requires to not only keep track of a *line* but also of the *position in the line*.
        if cmd not in ("cO", "cont"):
            raise BasicError("syntax")
        if self.cont_line_index is None or self.program_lines is None or not self.program:
            raise BasicError("can't continue")
        self.execute_run("run "+str(self.program_lines[self.cont_line_index+1]))

    def execute_poke(self, cmd):
        if cmd.startswith("pO"):
            cmd = cmd[2:]
        elif cmd.startswith("poke"):
            cmd = cmd[4:]
        addr, value = cmd.split(',', maxsplit=1)
        addr, value = eval(addr, self.symbols), int(eval(value, self.symbols))
        if addr < 0 or addr > 0xffff or value < 0 or value > 0xff:
            raise BasicError("illegal quantity")
        self.screen.setmem(addr, value)

    def execute_wpoke(self, cmd):
        if cmd.startswith("wpO"):
            cmd = cmd[3:]
        elif cmd.startswith("wpoke"):
            cmd = cmd[5:]
        addr, value = cmd.split(',', maxsplit=1)
        addr, value = eval(addr, self.symbols), int(eval(value, self.symbols))
        if addr < 0 or addr > 0xffff or addr & 1 or value < 0 or value > 0xffff:
            raise BasicError("illegal quantity")
        self.screen.setmem(addr, value, True)

    def execute_sys(self, cmd):
        if cmd.startswith("sY"):
            cmd = cmd[2:]
        elif cmd.startswith("sys"):
            cmd = cmd[3:]
        addr = int(cmd)
        if addr < 0 or addr > 0xffff:
            raise BasicError("illegal quantity")
        if addr in (64738, 64760):
            raise ResetMachineError()
        if addr == 58640:       # set cursorpos
            x, y = self.screen.getmem(211), self.screen.getmem(214)
            self.screen.cursormove(x, y)
        else:
            raise BasicError("no machine language support")

    def peek_func(self, address):
        if address < 0 or address > 0xffff:
            raise BasicError("illegal quantity")
        return self.screen.getmem(address)

    def wpeek_func(self, address):
        if address < 0 or address > 0xffff or address & 1:
            raise BasicError("illegal quantity")
        return self.screen.getmem(address, True)

    def execute_list(self, cmd):
        if cmd.startswith("lI"):
            cmd = cmd[2:]
        elif cmd.startswith("list"):
            cmd = cmd[4:]
        start, sep, to = cmd.partition("-")
        start = start.strip()
        if to:
            to = to.strip()
        if not self.program:
            return
        start = int(start) if start else 0
        to = int(to) if to else None
        self.screen.writestr("\r")
        for num, text in sorted(self.program.items()):
            if num < start:
                continue
            if to is not None and num > to:
                break
            self.screen.writestr("{:d} {:s}\r".format(num, text))

    def execute_new(self, cmd):
        if cmd.startswith("nE"):
            cmd = cmd[2:]
        elif cmd.startswith("new"):
            cmd = cmd[3:]
        if cmd:
            raise BasicError("syntax")
        self.program.clear()

    def execute_save(self, cmd):
        if cmd.startswith("sA"):
            cmd = cmd[2:]
        elif cmd.startswith("save"):
            cmd = cmd[4:]
        cmd = cmd.strip()
        if cmd.endswith("\",8,1"):
            cmd = cmd[:-4]
        elif cmd.endswith("\",8"):
            cmd = cmd[:-2]
        if not (cmd.startswith('"') and cmd.endswith('"')):
            raise BasicError("syntax")
        cmd = cmd[1:-1]
        if not cmd:
            raise BasicError("missing file name")
        if not self.program:
            return
        if not cmd.endswith(".bas"):
            cmd += ".bas"
        self.screen.writestr("\rsaving " + cmd)
        with open(os.path.join("drive8", cmd), "wt", newline=None) as file:
            for num, line in sorted(self.program.items()):
                file.write("{:d} {:s}\r".format(num, line))

    def execute_load(self, cmd):
        if cmd.startswith("lO"):
            cmd = cmd[2:]
        elif cmd.startswith("load"):
            cmd = cmd[4:]
        cmd = cmd.strip()
        if cmd.startswith("\"$\""):
            raise BasicError("use dos\"$ instead")
        if cmd.endswith(",8,1"):
            cmd = cmd[:-4]
        elif cmd.endswith(",8"):
            cmd = cmd[:-2]
        cmd = cmd.strip()
        if not (cmd.startswith('"') and cmd.endswith('"')):
            raise BasicError("syntax")
        filename = cmd[1:-1]
        self.screen.writestr("searching for " + filename + "\r")
        if not os.path.isfile(os.path.join("drive8", filename)):
            filename = filename + ".*"
        if filename.endswith('*'):
            # take the first file in the directory matching the pattern
            filename = glob.glob(os.path.join("drive8", filename))
            if not filename:
                raise BasicError("file not found")
            filename = os.path.basename(list(sorted(filename))[0])
        newprogram = {}
        num = 1
        try:
            with open(os.path.join("drive8", filename), "rt", newline=None) as file:
                self.screen.writestr("loading " + filename + "\r")
                for line in file:
                    line = line.rstrip()
                    if not line:
                        continue
                    if filename.endswith((".bas", ".BAS")):
                        num, line = line.split(maxsplit=1)
                        newprogram[int(num)] = line
                    else:
                        newprogram[num] = line.rstrip()
                        num += 1
        except FileNotFoundError:
            raise BasicError("file not found")
        self.program = newprogram
        return

    def execute_dos(self, cmd):
        cmd = cmd[4:]
        if cmd == "$":
            # show disk directory
            files = sorted(os.listdir("drive8"))
            catalog = ((file, os.path.getsize(os.path.join("drive8", file))) for file in files)
            header = "\"floppy contents \" ** 2a"
            self.screen.writestr("\r0 \x12"+header+"\x92\r")
            for file, size in sorted(catalog):
                name, suff = os.path.splitext(file)
                name = '"' + name + '"'
                self.screen.writestr("{:<5d}{:19s}{:3s}\r".format(size // 256, name, suff[1:]))
            self.screen.writestr("9999 blocks free.\r")
            return
        raise BasicError("syntax")

    def execute_run(self, cmd):
        cmd = cmd[3:]
        start = int(cmd) if cmd else None
        if start is not None and start not in self.program:
            raise BasicError("undef'd statement")
        if self.program:
            self.program_lines = list(sorted(self.program))
            self.cont_line_index = None
            self.current_run_line_index = 0 if start is None else self.program_lines.index(start)
            raise StartRunloop()

    def execute_if(self, cmd):
        match = re.match(r"if(.+)then(.+)$", cmd)
        if match:
            condition, then = match.groups()
            condition = eval(condition, self.symbols)
            if condition:
                self.execute_line(then, print_ready=False)
        else:
            # perhaps if .. goto .. form?
            match = re.match(r"if(.+)goto\s+(\d+)$", cmd)
            if not match:
                raise BasicError("syntax")
            condition, line = match.groups()
            condition = eval(condition, self.symbols)
            if condition:
                line = int(line)
                if line not in self.program:
                    raise BasicError("undef'd statement")
                raise GotoLine(line)

    def execute_read(self, cmd):
        if cmd.startswith("rE"):
            cmd = cmd[2:]
        elif cmd.startswith("read"):
            cmd = cmd[4:]
        varname = cmd.strip()
        if ',' in varname:
            raise BasicError("syntax")
        value = self.get_next_data()
        if value is None:
            raise BasicError("out of data")
        self.symbols[varname] = value

    def execute_restore(self, cmd):
        if cmd.startswith("reS"):
            cmd = cmd[3:]
        elif cmd.startswith("restore"):
            cmd = cmd[7:]
        if cmd:
            raise BasicError("syntax")
        self.data_line = None
        self.data_index = None

    def stop_run(self):
        if self.current_run_line_index is not None:
            self.cont_line_index = self.current_run_line_index
            self.current_run_line_index = None
            self.last_run_error = None

    def get_next_data(self):
        if self.data_line is None:
            # search first data statement in program
            self.data_index = 0
            for nr, line in sorted(self.program.items()):
                if line.lstrip().startswith(("dA", "data")):
                    self.data_line = nr
                    break
            else:
                return None
        try:
            data = self.program[self.data_line].split(maxsplit=1)[1]
            value = data.split(",")[self.data_index]
        except IndexError:
            # go to next line
            self.data_index = 0
            for nr, line in sorted(self.program.items()):
                if self.data_line < nr and line.lstrip().startswith(("dA", "data")):
                    self.data_line = nr
                    return self.get_next_data()
            else:
                return None
        else:
            self.data_index += 1
            return eval(value)


class EmulatorWindow(tkinter.Tk):
    def __init__(self, title):
        super().__init__()
        self.wm_title(title)
        self.geometry("+200+100")
        self.screen = ScreenAndMemory()
        self.repaint_only_dirty = True     # set to False if you're continuously changing most of the screen
        self.basic = BasicInterpreter(self.screen)
        self.canvas = tkinter.Canvas(self, width=128 + 40 * 16, height=128 + 25 * 16, borderwidth=0, highlightthickness=0)
        topleft = self.screencor((0, 0))
        botright = self.screencor((40, 25))
        self.screenrect = self.canvas.create_rectangle(topleft[0], topleft[1], botright[0], botright[1], outline="")
        self.create_charsets()
        # create the 1000 character bitmaps fixed on the canvas:
        self.charbitmaps = []
        for y in range(25):
            for x in range(40):
                cor = self.screencor((x, y))
                bm = self.canvas.create_bitmap(cor[0], cor[1], bitmap="@charset/normal-20.xbm",
                                               foreground="black", background="white", anchor=tkinter.NW, tags="charbitmap")
                self.charbitmaps.append(bm)
        self.bind("<KeyPress>", lambda event: self.keypress(*self._keyevent(event)))
        self.bind("<KeyRelease>", lambda event: self.keyrelease(*self._keyevent(event)))
        self.repaint()
        self.canvas.pack()
        self.after(self.screen.cursor_blink_rate, self.blink_cursor)
        self.after(self.screen.update_rate, self.screen_refresher)
        introtxt = self.canvas.create_text(topleft[0] + 320, topleft[0] + 180, text="pyc64 basic & function keys active", fill="white")
        self.after(2500, lambda: self.canvas.delete(introtxt))
        self.run_step_after = None

    def _keyevent(self, event):
        c = event.char
        if not c or ord(c) > 255:
            c = event.keysym
        return c, event.state, event.keycode, event.x, event.y

    def keypress(self, char, state, keycode, mousex, mousey):
        # print("keypress", repr(char), state, keycode)
        with_shift = state & 1
        with_control = state & 4
        with_alt = state & 8
        if char.startswith("Shift") and with_control or char.startswith("Control") and with_shift \
            or char == "??" and with_control and with_shift:
            # simulate SHIFT+COMMODORE_KEY to flip the charset
            self.screen.shifted = not self.screen.shifted

        if len(char) == 1:
            # if '1' <= char <= '8' and self.key_control_down:
            #     self.c64screen.text = ord(char)-1
            if char == '\r':    # RETURN key
                line = self.screen.current_line(2)
                self.screen.return_key()
                if not with_shift:
                    self.execute_line(line)
            elif char in ('\x08', '\x7f', 'Delete'):
                if with_shift:
                    self.screen.insert()
                else:
                    self.screen.backspace()
            elif char == '\x03' and with_control:  # ctrl+C
                self.runstop()
            elif char == '\x1b':    # esc
                self.runstop()
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
                if with_shift:
                    self.screen.clearscreen()
                else:
                    self.screen.cursormove(0, 0)
                self.repaint()
            elif char in ('Insert', 'Help'):
                self.screen.insert()
                self.repaint()
            elif char == 'F7':      # directory shortcut key
                self.screen.clearscreen()
                dir_cmd = "dos\"$"
                self.screen.writestr(dir_cmd + "\r")
                self.execute_line(dir_cmd)
            elif char == 'F5':      # load file shortcut key
                if with_shift:
                    load_cmd = "load \"*\",8: "
                    self.screen.writestr(load_cmd + "\r")
                    self.execute_line(load_cmd)
                else:
                    self.screen.writestr("load ")
                    x, y = self.screen.cursorpos()
                    self.screen.cursormove(x + 17, y)
                    self.screen.writestr(",8:   ")
                    line = self.screen.current_line(1)
                    self.screen.return_key()
                    self.execute_line(line)
            elif char == "F3":      # run program shortcut key
                self.screen.writestr("run: \r")
                self.execute_line("run")
            elif char == "F1":      # list program shortcut key
                self.screen.writestr("list: \r")
                self.execute_line("list")
            elif char == "Prior":     # pageup = RESTORE (outside running program)
                if self.basic.current_run_line_index is None:
                    self.screen.reset()
                    self.execute_line("? \"\";")

    def execute_line(self, line):
        try:
            self.basic.execute_line(line)
        except ResetMachineError:
            self.reset_machine()
            return False
        except StartRunloop:
            if self.run_step_after:
                raise BasicError("program already running")
            if self.basic.program:
                self.screen.cursor_enabled = False
                self.run_step_after = self.after_idle(self._do_run_step)
            else:
                self.screen.writestr("\rready.\r")
        except StopRunloop:
            if self.run_step_after:
                self.after_cancel(self.run_step_after)
                self.run_step_after = None
        except SleepTimer as sx:
            self.repaint()
            self.update_idletasks()  # repaint Tkinter window
            time.sleep(sx.args[0])
            if self.basic.current_run_line_index is None:
                self.screen.writestr("\rready.\r")
        return True

    def runstop(self):
        if self.basic.current_run_line_index is not None:
            line = self.basic.program_lines[self.basic.current_run_line_index]
            self.basic.stop_run()
            if self.run_step_after:
                self.after_cancel(self.run_step_after)
            self.run_step_after = None
            self.screen.writestr("\rbreak in {:d}\rready.\r".format(line))
            self.screen.cursor_enabled = True

    def keyrelease(self, char, state, keycode, mousex, mousey):
        # print("keyrelease", repr(char), state, keycode)
        pass

    def create_charsets(self):
        # normal
        source_chars = Image.open("charset/charset-normal.png")
        for i in range(256):
            filename = "charset/normal-{:02x}.xbm".format(i)
            if not os.path.isfile(filename):
                chars = source_chars.copy()
                row, col = divmod(i, 40)
                ci = chars.crop((col * 16, row * 16, col * 16 + 16, row * 16 + 16))
                ci = ci.convert(mode="1", dither=None)
                ci.save(filename, "xbm")
        # shifted
        source_chars = Image.open("charset/charset-shifted.png")
        for i in range(256):
            filename = "charset/shifted-{:02x}.xbm".format(i)
            if not os.path.isfile(filename):
                chars = source_chars.copy()
                row, col = divmod(i, 40)
                ci = chars.crop((col * 16, row * 16, col * 16 + 16, row * 16 + 16))
                ci = ci.convert(mode="1", dither=None)
                ci.save(filename, "xbm")

    def repaint(self):
        # set border color and screen color
        bordercolor = self.tkcolor(self.screen.border)
        screencolor = self.tkcolor(self.screen.screen)
        if self.canvas["bg"] != bordercolor:
            self.canvas["bg"] = bordercolor
        if self.canvas.itemcget(self.screenrect, "fill") != screencolor:
            self.canvas.itemconfigure(self.screenrect, fill=screencolor)
        style = "shifted" if self.screen.shifted else "normal"
        if self.repaint_only_dirty:
            dirty = iter(self.screen.getdirty())
        else:
            chars, colors = self.screen.getscreencopy()
            dirty = enumerate(zip(chars, colors))
        for index, (char, color) in dirty:
            forecol = self.tkcolor(color)
            bm = self.charbitmaps[index]
            bitmap = "@charset/{:s}-{:02x}.xbm".format(style, char)
            self.canvas.itemconfigure(bm, foreground=forecol, background=screencolor, bitmap=bitmap)

    def screencor(self, cc):
        return 64 + cc[0] * 16, 64 + cc[1] * 16

    def tkcolor(self, color):
        return "#{:06x}".format(ScreenAndMemory.palette[color % 16])

    def blink_cursor(self):
        if self.screen.cursor_enabled:
            self.screen.blink_cursor()
            # self.repaint()
        self.after(self.screen.cursor_blink_rate, self.blink_cursor)

    def screen_refresher(self):
        self.repaint()
        self.after(self.screen.update_rate, self.screen_refresher)

    def reset_machine(self):
        self.run_step_after = None
        self.screen.reset()
        self.screen.cursor_enabled = False

        def reset2():
            self.basic.reset()
            self.screen.cursor_enabled = True
            self.update()
        self.after(600, reset2)

    def _do_run_step(self):
        if self.basic.current_run_line_index is not None and self.basic.last_run_error is None:
            if self.basic.current_run_line_index < len(self.basic.program_lines):
                next_linenum = self.basic.program_lines[self.basic.current_run_line_index]
                line = self.basic.program[next_linenum]
                try:
                    go_on = self.execute_line(line)
                    if not go_on:
                        self.run_step_after = None
                        return
                    if self.basic.current_run_line_index is not None:
                        self.basic.current_run_line_index += 1
                except GotoLine as ex:
                    self.basic.current_run_line_index = self.basic.program_lines.index(ex.line)
                if self.basic.last_run_error is None and \
                        self.basic.current_run_line_index is not None and \
                        self.basic.current_run_line_index < len(self.basic.program_lines):
                    # Introduce an artificial delay here, to get at least *some*
                    # sense of the old times. Note that on windows it will be extremely slow somehow
                    # when you time it with after_idle, so we do a workaround there.
                    if sys.platform == "win32":
                        self.run_step_after = self.after(1, self._do_run_step)
                    else:
                        time.sleep(0.0001)
                        self.run_step_after = self.after_idle(self._do_run_step)
                    return
                else:
                    self.run_step_after = None
                    if not self.basic.last_run_error:
                        self.screen.writestr("\rready.\r")
            # program ends
            self.basic.stop_run()
            self.run_step_after = None
            self.screen.cursor_enabled = True


def setup():
    ScreenAndMemory.test_screencode_mappings()
    emu = EmulatorWindow("Fast Commodore-64 'emulator' in pure Python!")
    emu.mainloop()


if __name__ == "__main__":
    setup()

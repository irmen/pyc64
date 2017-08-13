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
import tkinter
import traceback
import numbers
import glob
import time
from PIL import Image


class C64ScreenAndMemory:
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

    # translate ascii strings to petscii codes:
    # (non-ascii symbols supported:  £ ↑ ⬆ ← ⬅ ♠ ♥ ♦ ♣ π ● ○ )
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
        '^': 30,        # up arrow
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
        '|': 94,    # pi symbol
        'π': 94,    # pi symbol
    })

    # the inverse, translate petscii back to ascii strings:
    c64_to_str_trans_normal = {v: k for k, v in str_to_64_trans.items()}
    c64_to_str_trans_shifted = {v: k for k, v in str_to_64_trans.items()}
    for c in range(ord('A'), ord('Z') + 1):
        c64_to_str_trans_shifted[c] = c
    c64_to_str_trans_normal[39] = c64_to_str_trans_shifted[39] = ord("'")

    def __init__(self):
        self.border = 0
        self.screen = 0
        self.text = 0
        self.shifted = False
        self.cursor = 0
        self.cursor_state = False
        self.cursor_blink_rate = 300
        self._cursor_enabled = True
        self.update_rate = 100
        # zeropage is from $0000-$00ff
        # screen chars     $0400-$07ff
        # screen colors    $d800-$dbff
        self._memory = [0] * 65536    # 64Kb of 'RAM'
        self._previous_checked_chars = None
        self._previous_checked_colors = None
        self.reset()

    def reset(self, hard=False):
        self.border = 14
        self.screen = 6
        self.text = 14
        self.shifted = False
        self.cursor = 0
        self.cursor_state = False
        self.cursor_blink_rate = 300
        self.cursor_enabled = True
        self._previous_checked_chars = None
        self._previous_checked_colors = None
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
            self._memory[53281] = self.screen
        elif address == 53272:
            self._memory[53272] = 23 if self.shifted else 21
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
                self._memory[0x0400 + cursor] = ord(c)
                self._memory[0xd800 + cursor] = self.text
                cursor += 1
                if cursor >= 1000:
                    self._scroll_up()
                    cursor -= 40
        self.cursor = cursor
        self._fix_cursor(on=True)

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

    def cursormove(self, x=0, y=0):
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
            self._memory[0xd800 + i] = self._colors[0xd800 - 1 + i]
        self._memory[0x0400 + self.cursor] = 32
        self._memory[0xd800 + self.cursor] = self.text
        self._fix_cursor(on=True)

    def current_line(self, amount=1):
        start = 0x0400 + 40 * (self.cursor // 40)
        self._fix_cursor()
        chars = "".join([chr(c) for c in self._memory[start:start + 40 * amount]])
        self._fix_cursor()
        trans = self.c64_to_str_trans_shifted if self.shifted else self.c64_to_str_trans_normal
        return chars.translate(trans)

    def inversevid(self, text, petscii=False):
        if not petscii:
            text = self.str2screen(text)
        return "".join(chr(128 + ord(c)) for c in text)

    def is_display_dirty(self):
        charmem = self._memory[0x0400:0x07e8]
        colormem = self._memory[0xd800:0xdbe8]
        result = charmem != self._previous_checked_chars or colormem != self._previous_checked_colors
        self._previous_checked_chars = charmem
        self._previous_checked_colors = colormem
        return result


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
        self.screen.writestr("\n    **** commodore 64 basic v2 ****\n")
        self.screen.writestr("\n 64k ram system  38911 basic bytes free\n")
        self.screen.writestr("\nready.\n")
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
            # print("RUN CMDS:", parts)  # XXX
            self.last_run_error = None
            if parts:
                for cmd in parts:
                    do_more = self._execute_cmd(cmd, parts)
                    if not do_more:
                        break
                if self.current_run_line_index is None and print_ready:
                    self.screen.writestr("\nready.\n")
        except FlowcontrolException:
            raise
        except BasicError as bx:
            if self.current_run_line_index is None:
                self.screen.writestr("\n?" + bx.args[0].lower() + "  error\nready.\n")
            else:
                self.last_run_error = bx.args[0].lower()
                line = self.program_lines[self.current_run_line_index]
                self.screen.writestr("\n?" + bx.args[0].lower() + "  error in {line:d}\nready.\n".format(line=line))
            traceback.print_exc()
        except Exception as ex:
            if self.current_run_line_index is not None:
                self.last_run_error = str(ex).lower()
            self.screen.writestr("\n?" + str(ex).lower() + "  error\nready.\n")
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
        print_newline = "\n"
        if cmd:
            if cmd.endswith((',', ';')):
                cmd = cmd[:-1]
                print_newline = ""
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
        self.screen.writestr(result + print_newline)

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
                self.screen.writestr("\nbreak in {:d}\n".format(self.program_lines[self.current_run_line_index]))
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
        self.screen.writestr("\n")
        for num, text in sorted(self.program.items()):
            if num < start:
                continue
            if to is not None and num > to:
                break
            self.screen.writestr("{:d} {:s}\n".format(num, text))

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
        self.screen.writestr("\nsaving " + cmd)
        with open(os.path.join("drive8", cmd), "wt", newline=None) as file:
            for num, line in sorted(self.program.items()):
                file.write("{:d} {:s}\n".format(num, line))

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
        self.screen.writestr("searching for " + filename + "\n")
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
                self.screen.writestr("loading " + filename + "\n")
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
            self.screen.writestr("\n0 " + self.screen.inversevid(header) + "\n", petscii=True)
            for file, size in sorted(catalog):
                name, suff = os.path.splitext(file)
                name = '"' + name + '"'
                self.screen.writestr("{:<5d}{:19s}{:3s}\n".format(size // 256, name, suff[1:]))
            self.screen.writestr("9999 blocks free.\n")
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
        self.screen = C64ScreenAndMemory()
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
        self.key_shift_down = False
        self.key_control_down = False
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
                line = self.screen.current_line(2)
                self.screen.return_key()
                self.execute_line(line)
            elif char == '\x7f':
                if self.key_shift_down:
                    self.screen.insert()
                else:
                    self.screen.backspace()
            elif char == '\x08':
                self.screen.backspace()
            elif char == '\x03' and self.key_control_down:  # ctrl+C
                self.runstop()
            elif char == '\x1b':    # esc
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
                    self.screen.cursormove()
                self.repaint()
            elif char == 'Insert':
                self.screen.insert()
                self.repaint()
            elif char == 'F7':      # directory shortcut key
                self.screen.clearscreen()
                dir_cmd = "dos\"$"
                self.screen.writestr(dir_cmd + "\n")
                self.execute_line(dir_cmd)
            elif char == 'F5':      # load file shortcut key
                if self.key_shift_down:
                    load_cmd = "load \"*\",8: "
                    self.screen.writestr(load_cmd + "\n")
                    self.execute_line(load_cmd)
                else:
                    self.screen.writestr("load ")
                    x, y = self.screen.cursorpos()
                    self.screen.cursormove(x + 17, y)
                    self.screen.writestr(",8:   ")
                    line = self.screen.current_line(1)
                    self.screen.return_key()
                    self.execute_line(line)
                    self.execute_line(line)
            elif char == "F3":      # run program shortcut key
                self.screen.writestr("run: \n")
                self.execute_line("run")
            elif char == "F1":      # list program shortcut key
                self.screen.writestr("list: \n")
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
                self.screen.writestr("\nready.\n")
        except StopRunloop:
            if self.run_step_after:
                self.after_cancel(self.run_step_after)
                self.run_step_after = None
        except SleepTimer as sx:
            self.repaint()
            self.update_idletasks()  # repaint Tkinter window
            time.sleep(sx.args[0])
            if self.basic.current_run_line_index is None:
                self.screen.writestr("\nready.\n")
        return True

    def runstop(self):
        if self.basic.current_run_line_index is not None:
            line = self.basic.program_lines[self.basic.current_run_line_index]
            self.basic.stop_run()
            if self.run_step_after:
                self.after_cancel(self.run_step_after)
            self.run_step_after = None
            self.screen.writestr("\nbreak in {:d}\nready.\n".format(line))
            self.screen.cursor_enabled = True

    def keyrelease(self, char, mouseposition):
        # print("keyrelease", repr(char), mouseposition)
        if char.startswith("Shift"):
            self.key_shift_down = False
        if char.startswith("Control"):
            self.key_control_down = False

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
        self.canvas["bg"] = self.tkcolor(self.screen.border)
        self.canvas.itemconfigure(self.screenrect, fill=self.tkcolor(self.screen.screen))
        if self.screen.is_display_dirty():
            bgcol = self.tkcolor(self.screen.screen)
            style = "shifted" if self.screen.shifted else "normal"
            for y in range(25):
                for x in range(40):
                    char, color = self.screen.getchar(x, y)
                    forecol = self.tkcolor(color)
                    bm = self.charbitmaps[x + y * 40]
                    bitmap = "@charset/{:s}-{:02x}.xbm".format(style, char)
                    self.canvas.itemconfigure(bm, foreground=forecol, background=bgcol, bitmap=bitmap)

    def screencor(self, cc):
        return 64 + cc[0] * 16, 64 + cc[1] * 16

    def tkcolor(self, color):
        return "#{:06x}".format(C64ScreenAndMemory.palette[color % 16])

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
                        self.screen.writestr("\nready.\n")
            # program ends
            self.basic.stop_run()
            self.run_step_after = None
            self.screen.cursor_enabled = True


def setup():
    emu = EmulatorWindow("Fast Commodore-64 emulator in pure Python!")
    emu.mainloop()


if __name__ == "__main__":
    setup()

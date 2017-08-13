import re
import os
import tkinter
import traceback
import numbers
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

    def current_line(self, amount=1):
        start = 40 * (self.cursor // 40)
        self._fix_cursor()
        chars = [chr(c) for c in self.chars[start:start+40*amount]]
        self._fix_cursor()
        trans = self.c64_to_str_trans_shifted if self.shifted else self.c64_to_str_trans_normal
        return ("".join(chars)).translate(trans)

    def inversevid(self, text, petscii=False):
        if not petscii:
            text = self.str2screen(text)
        return "".join(chr(128 + ord(c)) for c in text)


class BasicError(Exception):
    pass


class ResetMachineError(Exception):
    pass


class StartRunloop(Exception):
    pass


class GotoLine(Exception):
    def __init__(self, line):
        self.line = line


class BasicInterpreter:
    def __init__(self, screen):
        self.screen = screen
        self.program = {}
        self.reset()

    def reset(self):
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
            "pyro4": Pyro4,
            "peek": self.peek_func
        }
        for x in dir(math):
            if '_' not in x:
                self.symbols[x] = getattr(math, x)
        self.program = {
            10: "print \"hello\"",
            20: "goto 10"
        }
        self.screen.writestr("\n    **** commodore 64 basic v2 ****\n")
        self.screen.writestr("\n 64k ram system  38911 basic bytes free\n")
        self.screen.writestr("\nready.\n")
        self.stop_run()

    def execute_line(self, line):
        try:
            print("RUN LINE:", repr(line))
            # if there's no char on the last pos of the first line, only evaluate the first line
            if len(line) >= 40 and line[39] == ' ':
                line = line[:40]
            parts = [x for x in (p.strip() for p in line.split(":")) if x]
            print("RUN CMDS:", parts)  # XXX
            self.last_error = None
            if parts:
                for cmd in parts:
                    self._execute_cmd(cmd)
                if self.current_run_line_index is None:
                    self.screen.writestr("\nready.\n")
        except (ResetMachineError, StartRunloop, GotoLine):
            raise
        except BasicError as bx:
            self.last_error = bx.args[0].lower()
            if self.current_run_line_index is None:
                self.screen.writestr("\n?" + bx.args[0].lower() + "  error\nready.\n")
            else:
                line = self.program_lines[self.current_run_line_index]
                self.screen.writestr("\n?" + bx.args[0].lower() + "  error in {line:d}\nready.\n".format(line=line))
            traceback.print_exc()
        except Exception as ex:
            self.last_error = str(ex).lower()
            self.screen.writestr("\n?" + str(ex).lower() + "  error\nready.\n")
            traceback.print_exc()

    def _execute_cmd(self, cmd):
        if cmd.startswith("read") or cmd.startswith("rE"):
            raise BasicError("out of data")
        elif cmd.startswith("load") or cmd.startswith("lO"):
            self.execute_load(cmd)
        elif cmd.startswith(("print", "?")):
            self.execute_print(cmd)
        elif cmd.startswith(("poke", "pO")):
            self.execute_poke(cmd)
        elif cmd.startswith(("list", "lI")):
            self.execute_list(cmd)
        elif cmd.startswith(("new", "nI")):
            self.execute_new(cmd)
        elif cmd.startswith(("run", "rU")):
            self.execute_run(cmd)
        elif cmd.startswith(("sys", "sY")):
            self.execute_sys(cmd)
        elif cmd.startswith(("goto", "gO")):
            self.execute_goto(cmd)
        elif cmd == "cls":
            self.screen.clearscreen()
        elif cmd.startswith("dos\""):
            self.execute_dos(cmd)
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
            result = eval(cmd, self.symbols)
            if isinstance(result, numbers.Number):
                if result < 0:
                    result = str(result)
                else:
                    result = " "+str(result)
        else:
            result = ""
        self.screen.writestr(result + "\n")

    def execute_goto(self, cmd):
        if cmd.startswith("gO"):
            cmd = cmd[2:]
        elif cmd.startswith("goto"):
            cmd = cmd[4:]
        line = int(cmd)
        if self.current_run_line_index is None:
            # do a run instead
            self.execute_run("run "+str(line))
        else:
            if line not in self.program:
                raise BasicError("undef'd statement")
            raise GotoLine(line)

    def execute_poke(self, cmd):
        if cmd.startswith("pO"):
            cmd = cmd[2:]
        elif cmd.startswith("poke"):
            cmd = cmd[4:]
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
        elif addr == 53272:
            self.screen.shifted = value & 2
        elif addr == 53265:
            raise BasicError("screenmode switch not possible")

    def execute_sys(self, cmd):
        if cmd.startswith("sY"):
            cmd = cmd[2:]
        elif cmd.startswith("sys"):
            cmd = cmd[3:]
        addr = int(cmd)
        if addr in (64738, 64760):
            raise ResetMachineError()
        else:
            raise BasicError("no machine language support")

    def peek_func(self, address):
        if address == 646:
            return self.screen.text
        elif address == 53280:
            return self.screen.border
        elif address == 53281:
            return self.screen.screen
        elif address == 53272:
            return 23 if self.screen.shifted else 21
        elif 0x0400 <= address <= 0x07e7:
            return self.screen.chars[address - 0x0400]
        elif 0xd800 <= address <= 0xdbe7:
            return self.screen.colors[address - 0xd800]
        return 0

    def execute_list(self, cmd):
        if cmd.startswith("lI"):
            cmd = cmd[2:]
        elif cmd.startswith("list"):
            cmd = cmd[4:]
        start, sep, to = cmd.partition("-")
        print(start, sep, to)
        start = int(start) if start else 0
        to = int(to) if to else None
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

    def execute_load(self, cmd):
        if cmd.startswith("lO"):
            cmd = cmd[2:]
        elif cmd.startswith("load"):
            cmd = cmd[4:]
        if cmd.startswith("\"$\""):
            raise BasicError("use dos\"$ instead")
        if cmd.startswith('"') and cmd.endswith('"'):
            filename = cmd[1:-1]
            newprogram = {}
            num = 10
            try:
                with open(os.path.join("drive8", filename), "rt") as file:
                    for line in file:
                        newprogram[num] = line
                        num += 10
            except FileNotFoundError:
                raise BasicError("file not found")
            self.program = newprogram
            return
        raise BasicError("syntax")

    def execute_dos(self, cmd):
        cmd = cmd[4:]
        if cmd == "$":
            # show disk directory
            files = sorted(os.listdir("drive8"))
            catalog = ((file, os.path.getsize(os.path.join("drive8", file))) for file in files)
            header = "\"floppy contents \" **  2a"
            self.screen.writestr("\n0 "+self.screen.inversevid(header)+"\n", petscii=True)
            for file, size in sorted(catalog):
                self.screen.writestr("{:<5d}\"{:s}\"".format(size, file))
            self.screen.writestr("\n9999 blocks free.\n")
            return
        raise BasicError("syntax")

    def execute_run(self, cmd):
        cmd = cmd[3:]
        start = int(cmd) if cmd else None
        if start is not None and start not in self.program:
            raise BasicError("undef'd statement")
        self.program_lines = list(sorted(self.program))
        self.current_run_line_index = 0 if start is None else self.program_lines.index(start)
        raise StartRunloop()

    def stop_run(self):
        print("STOP RUNNING!!!!")  # XXX
        self.current_run_line_index = None
        self.program_lines = None
        self.last_error = None


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
        self.cursor_blink_after = self.after(self.screen.cursor_blink_rate, self.blink_cursor)
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

    def execute_line(self, line):
        try:
            self.basic.execute_line(line)
        except ResetMachineError:
            self.reset_machine()
        except StartRunloop:
            if self.run_step_after:
                raise BasicError("program already running")
            self.run_step_after = self.after(1, self._do_run_step)

    def runstop(self):
        print("runstop")
        if self.basic.current_run_line_index is not None:
            line = self.basic.program_lines[self.basic.current_run_line_index]
            self.basic.stop_run()
            if self.run_step_after:
                self.after_cancel(self.run_step_after)
            self.run_step_after = None
            self.screen.writestr("\nbreak in {:d}\nready.\n".format(line))

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
        self.cursor_blink_after = self.after(self.screen.cursor_blink_rate, self.blink_cursor)

    def reset_machine(self):
        if self.cursor_blink_after:
            self.after_cancel(self.cursor_blink_after)
        self.screen.reset()
        def reset2():
            self.basic.reset()
            self.cursor_blink_after = self.after(self.screen.cursor_blink_rate, self.blink_cursor)
            self.update()
        self.after(600, reset2)

    def _do_run_step(self):
        if self.basic.current_run_line_index is not None:
            if self.basic.current_run_line_index < len(self.basic.program_lines):
                next_linenum = self.basic.program_lines[self.basic.current_run_line_index]
                line = self.basic.program[next_linenum]
                try:
                    self.execute_line(line)
                    self.basic.current_run_line_index += 1
                except GotoLine as ex:
                    self.basic.current_run_line_index = self.basic.program_lines.index(ex.line)
                if self.basic.current_run_line_index < len(self.basic.program_lines):
                    self.run_step_after = self.after(1, self._do_run_step)
                    return
                else:
                    self.run_step_after = None
                    if not self.basic.last_error:
                        self.screen.writestr("\nready.\n")
            # program ends
            self.basic.stop_run()
            self.run_step_after = None


def setup():
    emu = EmulatorWindow("s1")
    emu.mainloop()


if __name__=="__main__":
    setup()

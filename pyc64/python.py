"""
Python REPL and program runner.

Written by Irmen de Jong (irmen@razorvine.net)
License: MIT open-source.
"""

import os
import sys
import traceback
from .shared import StdoutWrapper, do_load, do_dos, do_sys, FlowcontrolException


class ColorsProxy:
    def __init__(self, screen):
        self.screen = screen

    def __getitem__(self, item):
        if type(item) is slice:
            item = slice(item.start + 0xd800, item.stop + 0xd800, item.step)
            return self.screen.memory[item]
        x, y = int(item[0]), int(item[1])
        assert 0 <= x <= self.screen.columns and 0 <= y <= self.screen.rows, "position out of range"
        _, color = self.screen.getchar(x, y)
        return color

    def __setitem__(self, item, value):
        if type(item) is slice:
            item = slice(item.start + 0xd800, item.stop + 0xd800, item.step)
            self.screen.memory[item] = value
        else:
            x, y = int(item[0]), int(item[1])
            assert 0 <= x <= self.screen.columns and 0 <= y <= self.screen.rows, "position out of range"
            self.screen.memory[0xd800 + x + self.screen.columns * y] = value


class CharsProxy:
    def __init__(self, screen):
        self.screen = screen

    def __getitem__(self, item):
        if type(item) is slice:
            item = slice(item.start + 0x0400, item.stop + 0x0400, item.step)
            return self.screen.memory[item]
        x, y = int(item[0]), int(item[1])
        assert 0 <= x <= self.screen.columns and 0 <= y <= self.screen.rows, "position out of range"
        char, _ = self.screen.getchar(x, y)
        return char

    def __setitem__(self, item, value):
        if type(item) is slice:
            item = slice(item.start + 0x0400, item.stop + 0x0400, item.step)
            self.screen.memory[item] = value
        else:
            x, y = int(item[0]), int(item[1])
            assert 0 <= x <= self.screen.columns and 0 <= y <= self.screen.rows, "position out of range"
            self.screen.memory[0x0400 + x + self.screen.columns * y] = value


class PythonInterpreter:
    F1_list_command = "lprg()"
    F3_run_command = "run()"
    F5_load_command = ""
    F6_load_command = "load(\"*\",8)"
    F7_dir_command = "\fdos(\"$\")"

    def __init__(self, screen):
        self.screen = screen
        self.screen.shifted = True
        self.interactive = None   # will be set later, externally
        self.reset()

    def start(self):
        self.orig_stdout = sys.stdout
        sys.stdout = StdoutWrapper(self.screen)

    def stop(self):
        sys.stdout = self.orig_stdout

    def reset(self):
        self.sleep_until = None
        self.code_to_run = None
        self.must_run_stop = False
        self.program = ""
        self.symbols = {
            "screen": self.screen,
            "colors": ColorsProxy(self.screen),
            "chars": CharsProxy(self.screen),
            "mem": self.screen.memory,
            "os": os,
            "sys": sys,
            "dos": lambda arg: do_dos(self.screen, arg),
            "load": self.execute_load,
            "save": self.execute_save,
            "lprg": self.execute_listprogram,
            "run": self.execute_run,
            "new": self.execute_new,
            "call": self.execute_sys,
            "sync": lambda: self.check_run_stop(self.interactive.do_sync_command),
            "sprite": self.execute_sprite
        }
        self.screen.writestr("\n  **** COMMODORE 64 PYTHON {:d}.{:d}.{:d} ****\n".format(*sys.version_info[:3]))
        self.screen.writestr("\n use 'go64' to return to C64 BASIC V2.\n")
        self.write_prompt()

    @property
    def running_program(self):
        return self.code_to_run is not None

    def write_prompt(self, prefix="\n"):
        self.screen.writestr(prefix + ">>> ")

    def execute_listprogram(self):
        self.screen.writestr("\n")
        self.must_run_stop = False
        for line in self.program.splitlines(keepends=True):
            self.screen.writestr(line)
            if self.must_run_stop:
                self.screen.writestr("break\n")
                break
            self.interactive.do_sync_command()

    def execute_line(self, line, recursive=False):
        line = line.lstrip()
        if line.startswith(">>>"):
            line = line[3:]
        line = line.strip()
        if not line:
            self.write_prompt()
            return
        try:
            code = compile(line, "<input>", "single")
            exec(code, self.symbols)
            self.write_prompt()
        except FlowcontrolException:
            raise
        except Exception as ex:
            traceback.print_exc()
            self.screen.writestr("\n?" + str(ex).lower() + "  error\n")
            self.write_prompt()

    def program_step(self):
        try:
            code = compile(self.code_to_run, "<program>", "exec")
            exec(code, self.symbols)
        except KeyboardInterrupt:
            self.screen.writestr("\naborted.\n")
            self.write_prompt()
            self.must_run_stop = False
        except Exception as ex:
            traceback.print_exc()
            self.screen.writestr("\n?" + str(ex).lower() + "  error\n")
        finally:
            self.code_to_run = None

    def runstop(self):
        self.must_run_stop = True

    def execute_load(self, arg):
        program = do_load(self.screen, arg)
        if not isinstance(program, str):
            raise IOError("invalid file type")
        self.program = program

    def execute_save(self, arg):
        if not arg:
            raise ValueError("missing file name")
        if not self.program:
            return
        if not arg.endswith(".py"):
            arg += ".py"
        self.screen.writestr("\nsaving " + arg)
        with open("drive8/" + arg, "w", encoding="utf8") as file:
            file.write(self.program)

    def execute_run(self, arg=None):
        arg = arg or self.program
        if not arg:
            return
        self.must_run_stop = False
        self.code_to_run = arg or None

    def execute_new(self):
        self.program = ""

    def execute_sys(self, addr):
        do_sys(self.screen, addr)

    def execute_sprite(self, spritenum, x=None, y=None, dx=None, dy=None, color=None, enabled=None, pointer=None):
        assert 0 <= spritenum <= 7
        if x is None and y is None and dx is None and dy is None and color is None and enabled is None and pointer is None:
            # return sprite info instead
            return self.screen.getsprites([spritenum], bitmap=False)[spritenum]
        if x is not None:
            x = int(x)
            self.screen.memory[53248 + spritenum * 2] = x & 255
            xmsb = self.screen.memory[53264]
            if x > 255:
                self.screen.memory[53264] = xmsb | 1 << spritenum
            else:
                self.screen.memory[53264] = xmsb & ~(1 << spritenum)
        if y is not None:
            self.screen.memory[53249 + spritenum * 2] = int(y) & 255
        if dx is not None:
            flag = self.screen.memory[53277]
            if dx:
                self.screen.memory[53277] = flag | 1 << spritenum
            else:
                self.screen.memory[53277] = flag & ~(1 << spritenum)
        if dy is not None:
            flag = self.screen.memory[53271]
            if dy:
                self.screen.memory[53271] = flag | 1 << spritenum
            else:
                self.screen.memory[53271] = flag & ~(1 << spritenum)
        if color is not None:
            self.screen.memory[53287 + spritenum] = int(color)
        if enabled is not None:
            flag = self.screen.memory[53269]
            if enabled:
                self.screen.memory[53269] = flag | 1 << spritenum
            else:
                self.screen.memory[53269] = flag & ~(1 << spritenum)
        if pointer is not None:
            if pointer & 63:
                raise ValueError("sprite pointer must be 64-byte aligned")
            self.screen.memory[2040 + spritenum] = pointer // 64

    def check_run_stop(self, continuation, *args, **kwargs):
        if self.must_run_stop:
            self.must_run_stop = False
            raise KeyboardInterrupt("run/stop")
        continuation(*args, **kwargs)

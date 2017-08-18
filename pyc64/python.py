"""
Python REPL and program runner.

Written by Irmen de Jong (irmen@razorvine.net)
License: MIT open-source.
"""
import os
import sys
import traceback
from .shared import do_load, do_dos


class ColorsProxy:
    def __init__(self, screen):
        self.screen = screen

    def __getitem__(self, item):
        if type(item) is slice:
            return [self.screen.getmem(0x0400 + i) for i in range(*item.indices(1000))]
        x, y = int(item[0]), int(item[1])
        assert 0 <= x <= 40 and 0 <= y <= 25, "position out of range"
        _, color = self.screen.getchar(x, y)
        return color

    def __setitem__(self, item, value):
        if type(item) is slice:
            assert 0 <= item.start <= 1000 and 0 <= item.stop <= 1000, "position out of range"
            try:
                if len(value) > 1:
                    for vi, i in enumerate(range(*item.indices(1000))):
                        self.screen.setmem(0xd800 + i, value[vi])
                    return
            except TypeError:
                pass
            for i in range(*item.indices(1000)):
                self.screen.setmem(0xd800 + i, value)
            return
        x, y = int(item[0]), int(item[1])
        assert 0 <= x <= 40 and 0 <= y <= 25, "position out of range"
        self.screen.setmem(0xd800 + x + 40 * y, value)


class CharsProxy:
    def __init__(self, screen):
        self.screen = screen

    def __getitem__(self, item):
        if type(item) is slice:
            return [self.screen.getmem(0x0400 + i) for i in range(*item.indices(1000))]
        x, y = int(item[0]), int(item[1])
        assert 0 <= x <= 40 and 0 <= y <= 25, "position out of range"
        char, _ = self.screen.getchar(x, y)
        return char

    def __setitem__(self, item, value):
        if type(item) is slice:
            assert 0 <= item.start <= 1000 and 0 <= item.stop <= 1000, "position out of range"
            try:
                if len(value) > 1:
                    for vi, i in enumerate(range(*item.indices(1000))):
                        self.screen.setmem(0x0400 + i, value[vi])
                    return
            except TypeError:
                pass
            for i in range(*item.indices(1000)):
                self.screen.setmem(0x0400 + i, value)
            return
        x, y = int(item[0]), int(item[1])
        assert 0 <= x <= 40 and 0 <= y <= 25, "position out of range"
        self.screen.setmem(0x0400 + x + 40 * y, value)


class MemoryProxy:
    def __init__(self, screen):
        self.screen = screen

    def __getitem__(self, item):
        item = int(item)
        return self.screen.getmem(item)

    def __setitem__(self, item, value):
        item = int(item)
        self.screen.setmem(item, value)


class StdoutWrapper:
    def __init__(self, screen):
        self.screen = screen

    def write(self, text):
        self.screen.writestr(text)

    def flush(self):
        pass


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
        self.program = ""
        self.symbols = {
            "screen": self.screen,
            "colors": ColorsProxy(self.screen),
            "chars": CharsProxy(self.screen),
            "mem": MemoryProxy(self.screen),
            "os": os,
            "sys": sys,
            "dos": lambda arg: do_dos(self.screen, arg),
            "load": self.execute_load,
            "save": self.execute_save,
            "lprg": self.execute_listprogram,
            "run": self.execute_run,
            "cls": self.screen.clearscreen,
            'new': self.execute_new
        }
        self.screen.writestr("\n  **** COMMODORE 64 PYTHON {:d}.{:d}.{:d} ****\n".format(*sys.version_info[:3]))
        self.screen.writestr("\n 64K RAM TOTAL  63536 MEMORY BYTES FREE\n")
        self.screen.writestr("\n use 'go64' to return to C64 BASIC V2.\n")
        self.write_prompt()

    @property
    def running_program(self):
        return False

    def write_prompt(self, prefix="\n"):
        self.screen.writestr(prefix + ">>> ")

    def execute_listprogram(self):
        self.screen.writestr("\n" + self.program)

    def execute_line(self, line):
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
        except Exception as ex:
            traceback.print_exc()
            self.screen.writestr("\n?" + str(ex).lower() + "  error\n")
            self.write_prompt()

    def program_step(self):
        raise NotImplementedError

    def runstop(self):
        raise NotImplementedError

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
        try:
            code = compile(arg, "<program>", "exec")
            exec(code, self.symbols)
        except Exception as ex:
            traceback.print_exc()
            self.screen.writestr("\n?" + str(ex).lower() + "  error\n")

    def execute_new(self):
        self.program = ""

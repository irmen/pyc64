"""
Basic dialect interpreter.

Note: the basic dialect is woefully incomplete and the commands that
are provided are often not even compatible with their originals on the C64,
but they do try to support *some* of the BASIC 2.0 structure.

The most important thing that is missing is the ability to
to do any 'blocking' operation such as INPUT or WAIT.
(GET - to grab a single pressed key - is supported).
The SLEEP command is added more or less as a hack, to be able to at least
slow down the thing at certain points.

Written by Irmen de Jong (irmen@razorvine.net)
License: MIT open-source.
"""

import os
import math
import hashlib
import base64
import binascii
import sys
import platform
import random
import traceback
import re
import time
import numbers
from .shared import StdoutWrapper, do_load, do_dos, do_sys, FlowcontrolException


class BasicError(Exception):
    pass


class GotoLineException(FlowcontrolException):
    def __init__(self, line_idx):
        self.line_idx = line_idx


class TimeValProxy:
    def __init__(self, memory, hz):
        self.memory = memory
        self.hz = hz

    def __str__(self):
        secs = ((self.memory[160] << 16) + (self.memory[161] << 8) + self.memory[162]) / self.hz
        h, secs = divmod(secs, 3600)
        m, secs = divmod(secs, 60)
        return "{:02d}{:02d}{:02d}".format(int(h), int(m), int(secs))

    def __repr__(self):
        return self.__str__()

    def __int__(self):
        jiffies = (self.memory[160] << 16) + (self.memory[161] << 8) + self.memory[162]
        return jiffies


class BasicInterpreter:
    F1_list_command = "list:"
    F3_run_command = "run:"
    F5_load_command = "load "
    F6_load_command = "load \"*\",8: "
    F7_dir_command = "\fdos\"$"

    def __init__(self, screen):
        self.screen = screen
        self.interactive = None   # will be set later, externally
        self.program = {}
        self.reset()

    def start(self):
        pass

    def stop(self):
        pass

    def reset(self):
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
            "peekw": self.peekw_func,
            "rnd": lambda *args: random.random(),
            "rndi": random.randrange,
            "asc": ord,
            "ti": TimeValProxy(self.screen.memory, self.screen.hz),
            "time": TimeValProxy(self.screen.memory, self.screen.hz),
        }
        for x in dir(math):
            if '_' not in x:
                self.symbols[x] = getattr(math, x)
        self.program = {}
        self.forloops = {}
        self.data_line = None
        self.data_index = None
        self.next_run_line_idx = None
        self.program_lines = None
        self.sleep_until = None
        self.must_run_stop = False
        if not self.screen.using_roms:
            # only print the basic header when we're not using actual roms
            self.screen.writestr("\n    **** commodore 64 basic v2 ****\n")
            self.screen.writestr("\n 64k ram system  38911 basic bytes free\n")
            self.write_prompt("\n")
        self.stop_running_program()

    @property
    def running_program(self):
        return self.next_run_line_idx is not None

    def write_prompt(self, prefix=""):
        self.screen.writestr(prefix + "ready.\n")

    def execute_line(self, line, recursive=False):
        in_program = self.running_program
        try:
            if in_program:
                # we're running in a program, REM and DATA do nothing
                if line.startswith(("#", "rem") or line.startswith(("dA", "data"))):
                    if not recursive:
                        self.next_run_line_idx += 1
                    return
            else:
                # direct mode
                # if there's no char on the last pos of the first line, only evaluate the first line
                if len(line) >= self.screen.columns and line[self.screen.columns - 1] == ' ':
                    line = line[:self.screen.columns]
                if self.process_programline_entry(line):
                    return
                if line.startswith(("#", "rem")):
                    self.write_prompt("\n")
                    return
                if line.startswith(("dA", "data")):
                    raise BasicError("illegal direct")
            # execute the command(s) on the line
            parts = [x for x in (p.strip() for p in line.split(":")) if x]
            if parts:
                for cmd in parts:
                    if cmd == "" or cmd.startswith(("#", "rem", "dA", "data")):
                        continue
                    do_more = self._execute_cmd(cmd, parts)
                    if not do_more:
                        break
                if not self.running_program and not self.sleep_until and not self.must_run_stop:
                    self.write_prompt("\n")
            if self.running_program:
                if not recursive:
                    # schedule next line to be executed
                    self.next_run_line_idx += 1
        except GotoLineException as gx:
            self.implementGoto(gx)            
        except FlowcontrolException:
            if in_program:
                if not recursive:
                    # we do go to the next line...
                    self.next_run_line_idx += 1
            raise
        except BasicError as bx:
            traceback.print_exc()
            if not self.running_program:
                self.screen.writestr("\n?" + bx.args[0].lower() + "  error\n")
                self.write_prompt()
            else:
                line = self.program_lines[self.next_run_line_idx]
                self.screen.writestr("\n?" + bx.args[0].lower() + "  error in {line:d}\n".format(line=line))
                self.write_prompt()
            self.stop_running_program()
        except Exception as ex:
            traceback.print_exc()
            self.screen.writestr("\n?" + str(ex).lower() + "  error\n")
            self.write_prompt()
            self.stop_running_program()

    def implementGoto(self,gx: GotoLineException):
        self.next_run_line_idx = gx.line_idx

    def process_programline_entry(self, line):
        match = re.match("(\d+)(\s*.*)", line)
        if match:
            if self.running_program:
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

    def runstop(self):
        self.must_run_stop = True
        if not self.running_program:
            return
        if self.sleep_until:
            self.sleep_until = None
            line = self.program_lines[self.next_run_line_idx - 1]
        else:
            line = self.program_lines[self.next_run_line_idx]
        self.stop_running_program()
        self.screen.writestr("\nbreak in {:d}\n".format(line))
        self.write_prompt()

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
        elif cmd.startswith("pokew"):
            self.execute_pokew(cmd)
        elif cmd.startswith(("poke", "pO")):
            self.execute_poke(cmd)
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
        elif cmd.startswith(("on")):
            self.execute_on_goto_gosub(cmd)
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
        elif cmd.startswith(("get", "gE")):
            self.execute_get(cmd)
        elif cmd.startswith(("sleep", "sL")):
            self.execute_sleep(cmd, all_cmds_on_line)
        elif cmd.startswith(("scroll", "sC")):
            self.execute_scroll(cmd)
        elif cmd.startswith(("color", "coL")):
            self.execute_color(cmd)
        elif cmd.startswith(("cursor", "cU")):
            self.execute_cursor(cmd)
        elif cmd == "cls":
            self.screen.clear()    # basic V2:  ?chr$(147);
        elif cmd == "sync":
            self.interactive.do_sync_command()
        elif cmd == "monitor":
            self.execute_monitor(cmd)
        elif cmd.startswith("dos\""):
            self.execute_dos(cmd)
            return False
        elif cmd == "help":
            self.execute_help(cmd)
        else:
            match = re.match(r"([a-zA-Z]+[0-9]*)\s*=\s*(.+)", cmd)
            if match:
                # variable assignment
                symbol, value = match.groups()
                self.symbols[symbol] = eval(value, self.symbols)
                return True
            else:
                print("Syntax error:", cmd, file=sys.stderr)
                raise BasicError("syntax")
        return True

    def execute_help(self, cmd):
        self.screen.writestr("\nknown statements:\n")
        known = ["?", "print", "cls", "color", "cursor", "data", "dos", "end", "for", "get", "gopy",
                 "goto", 
                 "on...goto",
                 "if", "list", "load", "new", "next", "peek", "peekw", "poke", "pokew",
                 "read", "rem", "restore", "run", "save", "scroll", "sleep", "stop", "sys", "help",
                 "monitor", "sync"]
        for kw in sorted(known):
            self.screen.writestr("{:10s}".format(kw))
        self.screen.writestr("\n")

    def execute_print(self, cmd):
        if cmd.startswith("?"):
            cmd = cmd[1:]
        elif cmd.startswith("print"):
            cmd = cmd[5:]
        print_return = "\n"
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
            if not self.running_program:
                raise BasicError("illegal direct")    # we only support for loops in a program (with line numbers), not on the screen
            if all_cmds_on_line and len(all_cmds_on_line) > 1:
                raise BasicError("for not alone on line")    # we only can loop to for statements that are alone on their own line
            varname, start, to, step = match.groups()
            if step is None:
                step = "1"
            start = eval(start, self.symbols)
            to = eval(to, self.symbols)
            step = eval(step, self.symbols)

            def frange(start, to, step):
                yield start
                start += step
                if step >= 0:
                    while start <= to:
                        yield start
                        start += step
                else:
                    while start >= to:
                        yield start
                        start += step

            iterator = iter(frange(start, to, step))
            self.forloops[varname] = (self.next_run_line_idx, iterator)
            self.symbols[varname] = next(iterator)
        else:
            raise BasicError("syntax")

    def execute_next(self, cmd):
        if cmd.startswith("nE"):
            cmd = cmd[2:]
        elif cmd.startswith("next"):
            cmd = cmd[4:]
        varname = cmd.strip()
        if not self.running_program:
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
            self.next_run_line_idx = runline_index   # jump back to code at line after for loop

    def execute_get(self, cmd):
        if cmd.startswith("gE"):
            cmd = cmd[2:]
        elif cmd.startswith("get"):
            cmd = cmd[3:]
        if not self.running_program:
            raise BasicError("illegal direct")
        varname = cmd.strip()
        if not varname:
            raise BasicError("syntax")
        self.symbols[varname] = self.interactive.do_get_command()

    def execute_goto(self, cmd):
        if cmd.startswith("gO"):
            cmd = cmd[2:]
        elif cmd.startswith("goto"):
            cmd = cmd[4:]
        line = eval(cmd, self.symbols)    # allows jump tables via GOTO VAR
        if not self.running_program:
            # do a run instead
            self.execute_run("run " + str(line))
        else:
            if line not in self.program:
                raise BasicError("undef'd statement")
            raise GotoLineException(self.program_lines.index(line))
    """
    on <index-1-based> goto|gosub <line1>,<line2> 
    if index evaluate to 1 the execution proceed on line1

    """            
    def execute_on_goto_gosub(self,cmd):
        gosub=False
        if cmd.startswith("on"):
            cmd=cmd[2:]
        if cmd.find("goto")==-1 and cmd.find("gosub")==-1:
            raise BasicError("syntax")
        else:
            # Find out index list
            l2=(cmd[(cmd.find("go")+2):]).strip()
            # DEBUG print(l2)
            if l2.startswith("to"):
                # goto branch
                gosub=False
                targetLineList=l2[2:]
            elif l2.startswith("sub"):
                gosub=True
                targetLineList=l2[3:]
            else:
                raise BasicError("syntax")
        lineTargetTuple=targetLineList.strip().split(",")        
        goInx=cmd.find("go")
        expr=cmd[0:goInx]        
        # eval the on <expr> goto part
        onGoIndex=int(eval(expr,self.symbols))-1        
        line=int(lineTargetTuple[onGoIndex])
        if gosub==False:
            if not self.running_program:
                self.execute_run("run " + str(line))
            else:
                if line not in self.program:
                    raise BasicError("undef'd statement")
                raise GotoLineException(self.program_lines.index(line))               
        else:
            raise BasicError("gosub unsupported yet")
            # raise BasicError("syntax")


    def execute_sleep(self, cmd, all_cmds_on_line):
        if cmd.startswith("sL"):
            cmd = cmd[2:]
        elif cmd.startswith("sleep"):
            cmd = cmd[5:]
        if all_cmds_on_line and len(all_cmds_on_line) > 1:
            raise BasicError("sleep not alone on line")    # we only can SLEEP when it's on their own line
        howlong = eval(cmd, self.symbols)
        if howlong == 0:
            return
        if 0 < howlong <= 60:       # sleep value must be between 0 and 60 seconds
            self.sleep_until = time.time() + howlong
        else:
            raise BasicError("illegal quantity")

    def execute_scroll(self, cmd):
        # scroll [direction][,fillchar][,fillcolor][,amount] OR scroll direction,x1,y1,x2,y2[,fillchar][,fillcolor][,amount]
        if cmd.startswith("sC"):
            cmd = cmd[2:]
        elif cmd.startswith("scroll"):
            cmd = cmd[6:]
        direction = eval("(" + cmd + ")", self.symbols)
        scrolldir = 'u'
        x1, y1 = 0, 0
        x2, y2 = self.screen.columns - 1, self.screen.rows - 1
        fillsc = 32
        amount = 1
        fillcolor = self.screen.text
        if type(direction) is str:
            scrolldir = direction
        else:
            if len(direction) >= 5:
                scrolldir, x1, y1, x2, y2 = direction[0:5]
                if len(direction) >= 6:
                    fillsc = direction[5]
                if len(direction) >= 7:
                    fillcolor = direction[6]
                if len(direction) >= 8:
                    amount = direction[7]
                if len(direction) > 8:
                    raise BasicError("syntax")
            else:
                if len(direction) >= 1:
                    scrolldir = direction[0]
                if len(direction) >= 2:
                    fillsc = direction[1]
                if len(direction) >= 3:
                    fillcolor = direction[2]
                if len(direction) >= 4:
                    amount = direction[3]
                if len(direction) > 4:
                    raise BasicError("syntax")
        if x1 < 0 or x1 >= self.screen.columns or x2 < 0 or x2 >= self.screen.columns or\
                y1 < 0 or y1 >= self.screen.rows or y2 < 0 or y2 >= self.screen.rows:
            raise BasicError("illegal quantity")
        if amount <= 0 or amount > max(self.screen.columns, self.screen.rows):
            raise BasicError("illegal quantity")
        if scrolldir in ("u", "d", "l", "r", "ul", "ur", "dl", "dr", "lu", "ru", "ld", "rd"):
            self.screen.scroll((x1, y1), (x2, y2),
                               'u' in scrolldir, 'd' in scrolldir, 'l' in scrolldir, 'r' in scrolldir,
                               (fillsc, fillcolor), amount)
        else:
            raise BasicError("scroll direction")

    def execute_end(self, cmd):
        if cmd not in ("eN", "end", "sT", "stop"):
            raise BasicError("syntax")
        if self.running_program:
            if cmd in ("sT", "stop"):
                self.screen.writestr("\nbreak in {:d}\n".format(self.program_lines[self.next_run_line_idx]))
            self.stop_running_program()

    def execute_poke(self, cmd):
        if cmd.startswith("pO"):
            cmd = cmd[2:]
        elif cmd.startswith("poke"):
            cmd = cmd[4:]
        addr, value = cmd.split(',', maxsplit=1)
        addr, value = eval(addr, self.symbols), int(eval(value, self.symbols))
        if addr < 0 or addr > 0xffff or value < 0 or value > 0xff:
            raise BasicError("illegal quantity")
        self.screen.memory[int(addr)] = int(value)

    def execute_pokew(self, cmd):
        # 16-bits poke
        if cmd.startswith("pokew"):
            cmd = cmd[5:]
        addr, value = cmd.split(',', maxsplit=1)
        addr, value = eval(addr, self.symbols), int(eval(value, self.symbols))
        if addr < 0 or addr > 0xffff or addr & 1 or value < 0 or value > 0xffff:
            raise BasicError("illegal quantity")
        self.screen.memory.setword(int(addr), int(value))

    def execute_sys(self, cmd):
        if cmd.startswith("sY"):
            cmd = cmd[2:]
        elif cmd.startswith("sys"):
            cmd = cmd[3:]
        if not cmd:
            raise BasicError("syntax")
        addr = eval(cmd, self.symbols)
        try:
            do_sys(self.screen, addr, self.interactive._microsleep)
        except FlowcontrolException:
            raise
        except Exception as x:
            raise BasicError(str(x))

    def peek_func(self, address):
        if address < 0 or address > 0xffff:
            raise BasicError("illegal quantity")
        return self.screen.memory[address]

    def peekw_func(self, address):
        if address < 0 or address > 0xffff or address & 1:
            raise BasicError("illegal quantity")
        return self.screen.memory.getword(address)

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
        if start and not to and not sep:
            to = start
        start = int(start) if start else 0
        to = int(to) if to else None
        self.must_run_stop = False
        self.screen.writestr("\n")
        for num, text in sorted(self.program.items()):
            if num < start:
                continue
            if to is not None and num > to:
                break
            self.screen.writestr("{:d} {:s}\n".format(num, text))
            if self.must_run_stop:
                self.screen.writestr("break\n")
                break
            self.interactive.do_sync_command()

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
        with open("drive8/" + cmd, "w", encoding="utf8") as file:
            file.writelines("{:d} {:s}\n".format(num, line) for num, line in sorted(self.program.items()))

    def execute_load(self, cmd):
        if cmd.startswith("lO"):
            cmd = cmd[2:]
        elif cmd.startswith("load"):
            cmd = cmd[4:]
        try:
            program = do_load(self.screen, cmd)
        except Exception as x:
            raise BasicError(str(x))
        if program and not isinstance(program, dict):
            raise BasicError("invalid file type")
        self.program = program

    def execute_dos(self, cmd):
        # to show floppy contents without clobbering basic program like LOAD"$",8 would
        cmd = cmd[4:]
        do_dos(self.screen, cmd)

    def execute_run(self, cmd):
        cmd = cmd[3:]
        start = int(cmd) if cmd else None
        if start is not None and start not in self.program:
            raise BasicError("undef'd statement")
        if self.program:
            self.data_line = None
            self.data_index = None
            self.program_lines = list(sorted(self.program))
            raise GotoLineException(0 if start is None else self.program_lines.index(start))

    def execute_if(self, cmd):
        match = re.match(r"if(.+)then(.+)$", cmd)
        if match:
            condition, then = match.groups()
            condition = eval(condition, self.symbols)
            if condition:
                return self.execute_line(then, recursive=True)
        else:
            # perhaps if .. goto .. form?
            match = re.match(r"if(.+)goto\s+(\S+)$", cmd)
            if not match:
                raise BasicError("syntax")
            condition, line = match.groups()
            condition = eval(condition, self.symbols)
            if condition:
                line = eval(line, self.symbols)   # allows jumptables via GOTO VAR
                if line not in self.program:
                    raise BasicError("undef'd statement")
                raise GotoLineException(self.program_lines.index(line))

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

    def execute_color(self, cmd):
        # BASIC V2 equivalent:  poke 53280,c0: poke 53281, c1: poke 646, c2
        if cmd.startswith("coL"):
            cmd = cmd[3:]
        elif cmd.startswith("color"):
            cmd = cmd[5:]
        if cmd:
            colors = eval(cmd, self.symbols)
            if isinstance(colors, tuple):
                if len(colors) != 3:
                    raise BasicError("syntax")
                c1 = int(colors[0])
                c2 = int(colors[1])
                c3 = int(colors[2])
                if c1 > 255 or c2 > 255 or c3 > 255:
                    raise BasicError("illegal quantity")
                self.screen.border = c1
                self.screen.screen = c2
                self.screen.text = c3
                return
        raise BasicError("syntax")

    def execute_cursor(self, cmd):
        # BASIC V2 equivalent:  poke 211,x: poke 214,y: sys 58640
        if cmd.startswith("cU"):
            cmd = cmd[2:]
        elif cmd.startswith("cursor"):
            cmd = cmd[6:]
        if cmd:
            coords = eval(cmd, self.symbols)
            if isinstance(coords, tuple):
                if len(coords) != 2:
                    raise BasicError("syntax")
                x = int(coords[0]) % self.screen.columns
                y = int(coords[1]) % self.screen.rows
                self.screen.cursormove(x, y)
                return
        raise BasicError("syntax")

    def execute_monitor(self, cmd):
        if cmd.startswith("monitor"):
            cmd = cmd[7:]
        self.screen.writestr("starting monitor...(see console window)\n")
        self.screen.shifted = True
        from .cputools import Monitor
        stdout = StdoutWrapper(self.screen, duplicate=sys.stdout)
        mon = Monitor(memory=self.screen.memory, stdout=stdout)
        mon.onecmd("version")
        mon.cmdloop()
        self.screen.writestr("...back from monitor.\n")

    def stop_running_program(self):
        if self.running_program:
            self.next_run_line_idx = None
        self.sleep_until = None

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

    def program_step(self):
        # perform a discrete step of the running program
        if not self.running_program:
            return   # no program currently running
        if self.sleep_until is not None:
            # we're in a sleep call!
            if time.time() < self.sleep_until:
                return []
            self.sleep_until = None
        if self.next_run_line_idx >= len(self.program_lines):
            self.write_prompt("\n")
            self.stop_running_program()
        else:
            linenum = self.program_lines[self.next_run_line_idx]
            line = self.program[linenum]
            self.execute_line(line)

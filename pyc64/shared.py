"""
commands shared by BASIC V2 and Python interpreter.
"""

import re
import os
import struct
import glob


class StdoutWrapper:
    def __init__(self, screen, duplicate=None):
        self.screen = screen
        self.duplicate = duplicate

    def write(self, text):
        self.screen.writestr(text)
        if self.duplicate:
            self.duplicate.write(text)

    def flush(self):
        if self.duplicate:
            self.duplicate.flush()


class FlowcontrolException(Exception):
    pass


class ResetMachineException(FlowcontrolException):
    pass


def do_dos(screen, arg):
    # show disk directory
    if arg != "$":
        raise ValueError("only \"$\" understood for now")
    files = sorted(os.listdir("drive8"))
    catalog = ((file, os.path.getsize("drive8/" + file)) for file in files if os.path.isfile("drive8/" + file))
    header = "\"floppy contents \" ** 2a"
    screen.writestr("\n0 \uf11a" + header + "\uf11b\n")
    for file, size in sorted(catalog):
        name, suff = os.path.splitext(file)
        name = '"' + name + '"'
        screen.writestr("{:<5d}{:19s}{:3s}\n".format(size // 256, name, suff[1:]))
    screen.writestr("9999 blocks free.\n")


def do_load(screen, arg):
    # load a BASIC .bas or Python .py or C64 .prg file
    if not arg:
        raise ValueError("missing filename")
    if arg.startswith("\"$\""):
        raise ValueError("use dos\"$ instead")
    match = re.match(r'\s*"(.+)"', arg)
    if not match:
        match = re.match(r'\s*(.+)', arg)
        if not match:
            raise ValueError("missing filename")
    filename = match.groups()[0]
    screen.writestr("searching for " + filename + "\n")
    if not os.path.isfile("drive8/" + filename):
        filename = filename + ".*"
    if filename.endswith('*'):
        # take the first file in the directory matching the pattern
        filename = glob.glob("drive8/" + filename)
        if not filename:
            raise FileNotFoundError("file not found")
        filename = os.path.basename(list(sorted(filename))[0])
    if filename.endswith(".py"):
        with open("drive8/" + filename, "r", newline=None, encoding="utf8") as file:
            screen.writestr("loading " + filename + "\n")
            return file.read()
    elif filename.endswith(".bas"):
        newprogram = {}
        with open("drive8/" + filename, "r", newline=None, encoding="utf8") as file:
            screen.writestr("loading " + filename + "\n")
            for line in file:
                line = line.rstrip()
                if not line:
                    continue
                num, line = line.split(maxsplit=1)
                newprogram[int(num)] = line
        return newprogram
    elif filename.endswith(".prg"):
        with open("drive8/" + filename, "rb") as file:
            address = struct.unpack("<H", file.read(2))[0]
            prog = file.read()
        screen.writestr("loading from ${:04x} to ${:04x}...\n".format(address, address + len(prog)))
        screen.memory[address: address + len(prog)] = prog
        visible = b" abcdefghijklmnopqrstuvwxyz1234567890-=`~!@#$%^&*()_+[];:'\",.<>/?"
        return {
            0: "list 3-",
            1: "end",
            3: "---------------",
            4: "a .prg has been loaded.",
            5: "no support for listing these!",
            6: "maybe it contains machine code",
            7: "that you can call via sys...",
            8: "the first 30 printable chars are:",
            9: ">>> " + "".join(chr(x) if x in visible else ' ' for x in screen.memory[address: address + 30]),
            10: "(usually a sys address is shown)",
            11: "---------------",
        }
    else:
        raise IOError("unknown file type")


def do_sys(screen, addr, microsleep=None, use_rom_routines=False):
    if addr < 0 or addr > 0xffff:
        raise ValueError("illegal quantity")
    if not use_rom_routines:
        if addr in (64738, 64760):
            raise ResetMachineException()
        if addr == 58640:       # set cursorpos
            x, y = screen.memory[211], screen.memory[214]
            screen.cursormove(x, y)
            return
        elif addr in (58629, 65517):    # kernel SCREEN (get screen size X=colums Y=rows)
            screen.memory[0x30d] = screen.columns
            screen.memory[0x30e] = screen.rows
            return
        elif addr in (65520, 58634):    # kernel PLOT (get/set cursorpos)
            if screen.memory[0x030f] & 1:
                # carry set, read position
                x, y = screen.cursorpos()
                screen.memory[211], screen.memory[214] = x, y
                screen.memory[0x030e], screen.memory[0x030d] = x, y
            else:
                # carry clear, set position
                x, y = screen.memory[0x030e], screen.memory[0x030d]
                screen.memory[211], screen.memory[214] = x, y
                screen.cursormove(x, y)
            return
    from .cputools import CPU
    cpu = CPU(memory=screen.memory, pc=addr)
    # read A,X,Y and P from the ram
    cpu.a, cpu.x, cpu.y, cpu.p = screen.memory[0x030c:0x0310]
    try:
        cpu.run(microsleep=microsleep)
    finally:
        # store result A,X,Y and P back to ram
        screen.memory[0x030c:0x0310] = cpu.a, cpu.x, cpu.y, cpu.p

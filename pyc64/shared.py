"""
commands shared by BASIC V2 and Python interpreter.
"""

import re
import os
import glob


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
    screen.writestr("\n0 \x12" + header + "\x92\n")
    for file, size in sorted(catalog):
        name, suff = os.path.splitext(file)
        name = '"' + name + '"'
        screen.writestr("{:<5d}{:19s}{:3s}\n".format(size // 256, name, suff[1:]))
    screen.writestr("9999 blocks free.\n")


def do_load(screen, arg):
    # load a BASIC .bas or Python .py file
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
    if filename.endswith((".py", ".PY")):
        with open("drive8/" + filename, "r", newline=None, encoding="utf8") as file:
            screen.writestr("loading " + filename + "\n")
            return file.read()
    if filename.endswith((".bas", ".BAS")):
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
    raise IOError("unknown file type")


def do_sys(screen, addr):
    if addr < 0 or addr > 0xffff:
        raise ValueError("illegal quantity")
    if addr in (64738, 64760):
        raise ResetMachineException()
    if addr == 58640:       # set cursorpos
        x, y = screen.getmem(211), screen.getmem(214)
        screen.cursormove(x, y)
    else:
        raise NotImplementedError("no machine language support")

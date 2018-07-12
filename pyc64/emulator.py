"""
Commodore-64 simulator in 100% pure Python 3.x :)

This module is the GUI window logic, handling keyboard input
and screen drawing via tkinter bitmaps.

Written by Irmen de Jong (irmen@razorvine.net)
License: MIT open-source.
"""

import io
import os
import sys
import tkinter
import pkgutil
import threading
import queue
import time
from collections import deque
from PIL import Image
from .memory import ScreenAndMemory
from .basic import BasicInterpreter
from .shared import ResetMachineException, do_sys
from .python import PythonInterpreter


def create_bitmaps_from_char_rom(temp_graphics_folder, roms_directory):
    # create char bitmaps from the orignal c-64 chargen rom file
    rom = open(roms_directory+"/chargen", "rb").read()
    def doublewidth_and_mirror(b):
        result = 0
        for _ in range(8):
            bit = b&1
            b >>= 1
            result <<= 1
            result |= bit
            result <<= 1
            result |= bit
        x, y = divmod(result, 256)
        return y, x
    def writechar(c, rom_offset, filesuffix):
        with open("{:s}/char{:s}-{:02x}.xbm".format(temp_graphics_folder, filesuffix, c), "wb") as outf:
            outf.write(b"#define im_width 16\n")
            outf.write(b"#define im_height 16\n")
            outf.write(b"static char im_bits[] = {\n")
            for y in range(8):
                b1, b2 = doublewidth_and_mirror(rom[c*8 + y + rom_offset])
                outf.write(bytes("0x{:02x}, 0x{:02x}, 0x{:02x}, 0x{:02x}, ".format(b1, b2, b1, b2), "ascii"))
            outf.seek(-2, os.SEEK_CUR)  # get rid of the last space and comma
            outf.write(b"\n};\n")
    # normal chars
    for c in range(256):
        writechar(c, 0, "")
    # shifted chars
    for c in range(256):
        writechar(c, 256*8, "-sh")


class EmulatorWindowBase(tkinter.Tk):
    temp_graphics_folder = "temp_gfx"
    update_rate = 1000 // 20    # 20 hz screen refresh rate
    columns = 0
    rows = 0
    bordersize = 0
    sprites = 0
    smoothscrolling = True
    windowgeometry = "+200+40"
    charset_normal = "charset-normal.png"
    charset_shifted = "charset-shifted.png"
    colorpalette = []
    welcome_message = "Welcome to the simulator!"

    def __init__(self, screen, title, roms_directory):
        if len(self.colorpalette) not in (2, 4, 8, 16, 32, 64, 128, 256):
            raise ValueError("colorpalette size not a valid power of 2")
        if self.columns <= 0 or self.columns > 128 or self.rows <= 0 or self.rows > 128:
            raise ValueError("row/col size invalid")
        if self.bordersize < 0 or self.bordersize > 256:
            raise ValueError("bordersize invalid")
        if self.sprites < 0 or self.sprites > 256:
            raise ValueError("sprites invalid")
        super().__init__()
        self.wm_title(title)
        self.appicon = tkinter.PhotoImage(data=pkgutil.get_data(__name__, "icon.gif"))
        self.wm_iconphoto(self, self.appicon)
        if sys.platform == "win32":
            # tell windows to use a new toolbar icon
            import ctypes
            myappid = 'net.Razorvine.Tale.story'  # arbitrary string
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        self.geometry(self.windowgeometry)
        self.screen = screen
        self.canvas = tkinter.Canvas(self, width=2 * self.bordersize + self.columns * 16, height=2 * self.bordersize + self.rows * 16,
                                     borderwidth=0, highlightthickness=0, background="black",
                                     xscrollincrement=1, yscrollincrement=1)
        self.buttonbar = tkinter.Frame(self)
        resetbut1 = tkinter.Button(self.buttonbar, text="reset", command=self.reset_machine)
        resetbut1.pack(side=tkinter.LEFT)
        self.buttonbar.pack(fill=tkinter.X)
        self.refreshtick = threading.Event()
        self.spritebitmapbytes = [None] * self.sprites
        self.spritebitmaps = []
        self.roms_directory = roms_directory
        self.create_bitmaps(self.roms_directory)
        # create the character bitmaps for all character tiles, fixed on the canvas:
        self.charbitmaps = []
        for y in range(self.rows):
            for x in range(self.columns):
                cor = self.screencor((x, y))
                bm = self.canvas.create_bitmap(cor[0], cor[1], bitmap="@" + self.temp_graphics_folder + "/char-20.xbm",
                                               foreground="white", background="black", anchor=tkinter.NW, tags="charbitmap")
                self.charbitmaps.append(bm)
        # create the sprite tkinter bitmaps:
        for i in range(self.sprites - 1, -1, -1):
            cor = self.screencor_sprite((30 + i * 20, 140 + i * 10))
            bm = self.canvas.create_bitmap(cor[0], cor[1], bitmap="@{:s}/sprite-{:d}.xbm".format(self.temp_graphics_folder, i),
                                           foreground=self.tkcolor(i + 8), background=None, anchor=tkinter.NW, tags="spritebitmap")
            self.spritebitmaps.insert(0, bm)
        # the borders:
        if self.bordersize > 0:
            b1, b2, b3, b4 = self._border_positions()
            self.border1 = self.canvas.create_rectangle(*b1, outline="", fill="#000")
            self.canvas.tag_raise(self.border1)
            self.border2 = self.canvas.create_rectangle(*b2, outline="", fill="#000")
            self.canvas.tag_raise(self.border2)
            self.border3 = self.canvas.create_rectangle(*b3, outline="", fill="#000")
            self.canvas.tag_raise(self.border3)
            self.border4 = self.canvas.create_rectangle(*b4, outline="", fill="#000")
            self.canvas.tag_raise(self.border4)
        self.bind("<KeyPress>", self.keypress)
        self.bind("<KeyRelease>", self.keyrelease)
        self.canvas.pack()

    def start(self):
        self._cyclic_repaint()
        self._welcome_message()

    def _welcome_message(self):
        if self.welcome_message:
            topleft = self.screencor((0, 0))
            introtxt = self.canvas.create_text(topleft[0] + 16 * self.columns // 2, topleft[0] + 16 * (self.rows // 2 - 2),
                                               fill="white", justify=tkinter.CENTER,
                                               text=self.welcome_message)
            self.after(4000, lambda: self.canvas.delete(introtxt))

    def _cyclic_repaint(self):
        starttime = time.perf_counter()
        self.repaint()
        duration = time.perf_counter() - starttime
        remaining_timer_budget = (self.update_rate/1000)-duration
        if remaining_timer_budget < 0.001:
            print("warning: screen refresh took too long! ", remaining_timer_budget, file=sys.stderr)
            remaining_timer_budget = 0.001
        self.cyclic_repaint_after = self.after(int(remaining_timer_budget * 1000), self._cyclic_repaint)

    def keypress(self, event):
        pass   # override in subclass

    def keyrelease(self, event):
        pass   # override in subclass

    def repaint(self):
        # set bordercolor, done by setting the 4 border rectangles
        # (screen color done by setting the background color of all character bitmaps,
        #  this is a lot faster than using many transparent bitmaps!)
        if self.bordersize > 0:
            bordercolor = self.tkcolor(self.screen.border)
            if self.canvas.itemcget(self.border1, "fill") != bordercolor:
                self.canvas.itemconfigure(self.border1, fill=bordercolor)
                self.canvas.itemconfigure(self.border2, fill=bordercolor)
                self.canvas.itemconfigure(self.border3, fill=bordercolor)
                self.canvas.itemconfigure(self.border4, fill=bordercolor)
            # adjust borders
            bc1_new, bc2_new, bc3_new, bc4_new = self._border_positions()
            bc1 = self.canvas.coords(self.border1)
            bc2 = self.canvas.coords(self.border2)
            bc3 = self.canvas.coords(self.border3)
            bc4 = self.canvas.coords(self.border4)
            if bc1_new != bc1:
                self.canvas.coords(self.border1, bc1_new)
            if bc2_new != bc2:
                self.canvas.coords(self.border2, bc2_new)
            if bc3_new != bc3:
                self.canvas.coords(self.border3, bc3_new)
            if bc4_new != bc4:
                self.canvas.coords(self.border4, bc4_new)
        # characters
        prefix = "char-sh" if self.screen.shifted else "char"
        dirty = self.screen.getdirty()
        screencolor = self.tkcolor(self.screen.screen)
        for index, (char, color) in dirty:
            forecol = self.tkcolor(color)
            bm = self.charbitmaps[index]
            bitmap = "@{:s}/{:s}-{:02x}.xbm".format(self.temp_graphics_folder, prefix, char)
            self.canvas.itemconfigure(bm, foreground=forecol, background=screencolor, bitmap=bitmap)
        # smooth scroll
        if self.smoothscrolling:
            xys = self.smoothscroll(self.screen.scrollx, self.screen.scrolly)
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)
            self.canvas.xview_scroll(xys[0], tkinter.UNITS)
            self.canvas.yview_scroll(xys[1], tkinter.UNITS)
        # sprites
        sprites = self.screen.getsprites()
        for snum, sprite in sprites.items():
            configure = {}
            # sprite double sizes
            current_bm = self.canvas.itemcget(self.spritebitmaps[snum], "bitmap")
            extension = "-2x" if sprite.doublex else ""
            extension += "-2y" if sprite.doubley else ""
            if sprite.doublex != ("-2x" in current_bm) or sprite.doubley != ("-2y" in current_bm):
                # size change
                configure["bitmap"] = "@{:s}/sprite-{:d}{:s}.xbm".format(self.temp_graphics_folder, snum, extension)
            # bitmapdata
            if sprite.bitmap != self.spritebitmapbytes[snum]:
                # regenerate sprite bitmap
                self.create_sprite_bitmap(snum, sprite.bitmap)
                self.spritebitmapbytes[snum] = sprite.bitmap
                # first, configure another bitmap to force the old one out
                self.canvas.itemconfigure(self.spritebitmaps[snum], bitmap="@{:s}/char-00.xbm".format(self.temp_graphics_folder))
                # schedule reloading the sprite bitmap:
                configure["bitmap"] = "@{:s}/sprite-{:d}{:s}.xbm".format(self.temp_graphics_folder, snum, extension)
            # sprite enabled
            tkstate = tkinter.NORMAL if sprite.enabled else tkinter.HIDDEN
            if self.canvas.itemcget(self.spritebitmaps[snum], "state") != tkstate:
                configure["state"] = tkstate
            # sprite colors
            spritecolor = self.tkcolor(sprite.color)
            if self.canvas.itemcget(self.spritebitmaps[snum], "foreground") != spritecolor:
                configure["foreground"] = spritecolor
            # sprite positions
            x, y = self.screencor_sprite((sprite.x, sprite.y))
            self.canvas.coords(self.spritebitmaps[snum], x - 2 * self.screen.scrollx, y - 2 * self.screen.scrolly)
            if configure:
                # reconfigure all changed properties in one go
                self.canvas.itemconfigure(self.spritebitmaps[snum], **configure)
        self.refreshtick.set()

    def smoothscroll(self, xs, ys):
        return -xs * 2, -self.ys * 2

    def create_bitmaps(self, roms_directory=""):
        os.makedirs(self.temp_graphics_folder, exist_ok=True)
        with open(self.temp_graphics_folder + "/readme.txt", "w") as f:
            f.write("this is a temporary folder to cache pyc64 files for tkinter graphics bitmaps.\n")
        if roms_directory and os.path.isfile(roms_directory+"/chargen"):
            # create char bitmaps from the C64 chargen rom file.
            print("creating char bitmaps from chargen rom")
            create_bitmaps_from_char_rom(self.temp_graphics_folder, roms_directory)
        else:
            if roms_directory:
                print("creating char bitmaps from png images in the package (consider supplying {:s}/chargen ROM file)".format(roms_directory))
            else:
                print("creating char bitmaps from png images in the package")
            # normal
            with Image.open(io.BytesIO(pkgutil.get_data(__name__, "charset/" + self.charset_normal))) as source_chars:
                for i in range(256):
                    filename = self.temp_graphics_folder + "/char-{:02x}.xbm".format(i)
                    chars = source_chars.copy()
                    row, col = divmod(i, source_chars.width // 16)        # we assume 16x16 pixel chars (2x zoom)
                    ci = chars.crop((col * 16, row * 16, col * 16 + 16, row * 16 + 16))
                    ci = ci.convert(mode="1", dither=None)
                    ci.save(filename, "xbm")
            # shifted
            with Image.open(io.BytesIO(pkgutil.get_data(__name__, "charset/" + self.charset_shifted))) as source_chars:
                for i in range(256):
                    filename = self.temp_graphics_folder + "/char-sh-{:02x}.xbm".format(i)
                    chars = source_chars.copy()
                    row, col = divmod(i, source_chars.width // 16)        # we assume 16x16 pixel chars (2x zoom)
                    ci = chars.crop((col * 16, row * 16, col * 16 + 16, row * 16 + 16))
                    ci = ci.convert(mode="1", dither=None)
                    ci.save(filename, "xbm")
        # monochrome sprites (including their double-size variants)
        sprites = self.screen.getsprites()
        for i, sprite in sprites.items():
            self.create_sprite_bitmap(i, sprite.bitmap)
            self.spritebitmapbytes[i] = sprite.bitmap

    def _border_positions(self):
        if self.smoothscrolling:
            sx, sy = self.smoothscroll(self.screen.scrollx, self.screen.scrolly)
        else:
            sx, sy = 0, 0
        return [
            [sx, sy,
                2 * self.bordersize + self.columns * 16 + sx, self.bordersize + sy],
            [self.bordersize + self.columns * 16 + sx, self.bordersize + sy,
                2 * self.bordersize + self.columns * 16 + sx, self.bordersize + self.rows * 16 + sy],
            [sx, self.bordersize + self.rows * 16 + sy,
                2 * self.bordersize + self.columns * 16 + sx, 2 * self.bordersize + self.rows * 16 + sy],
            [sx, self.bordersize + sy,
                self.bordersize + sx, self.bordersize + self.rows * 16 + sy]
        ]

    def screencor(self, cxy):
        return self.bordersize + cxy[0] * 16, self.bordersize + cxy[1] * 16

    def screencor_sprite(self, cxy):
        return self.bordersize + cxy[0] * 2, self.bordersize + cxy[1] * 2

    def tkcolor(self, color):
        return "#{:06x}".format(self.colorpalette[color & len(self.colorpalette) - 1])

    def create_sprite_bitmap(self, spritenum, bitmapbytes):
        raise NotImplementedError("implement in subclass")

    def reset_machine(self):
        self.screen.reset(False)
        self.repaint()


class C64EmulatorWindow(EmulatorWindowBase):
    columns = 40
    rows = 25
    bordersize = 52
    sprites = 8
    colorpalette = ScreenAndMemory.colorpalette_pepto
    welcome_message = "pyc64 basic & function keys active\n\n" \
                      "use 'gopy' to enter Python mode\n\n\n\n" \
                      "(install the py64 library to be able to execute 6502 machine code)"

    def __init__(self, screen, title, roms_directory):
        super().__init__(screen, title, roms_directory)
        self.screen.memory[0x00fb] = EmulatorWindowBase.update_rate
        self.hertztick = threading.Event()
        self.interpret_thread = None
        self.interpreter = None

    def start(self):
        super().start()
        self._cyclic_herztick()
        self._cyclic_blink_cursor()
        self.reset_machine()

    def _cyclic_herztick(self):
        self.after(1000 // self.screen.hz, self._cyclic_herztick)
        self.screen.hztick()
        self.hertztick.set()

    def _cyclic_blink_cursor(self):
        self.cyclic_blink_after = self.after(self.screen.cursor_blink_rate, self._cyclic_blink_cursor)
        self.screen.blink_cursor()

    @property
    def update_rate(self):
        return max(10, self.screen.memory[0x00fb])

    joystick_keys_sane_platforms = {
        "Control_R": "fire",
        "KP_Insert": "fire",
        "KP_0": "fire",
        "KP_Enter": "fire",
        "Alt_R": "fire",
        "KP_Up": "up",
        "KP_8": "up",
        "KP_Down": "down",
        "KP_2": "down",
        "KP_Left": "left",
        "KP_4": "left",
        "KP_Right": "right",
        "KP_6": "right",
        "KP_Home": "leftup",
        "KP_7": "leftup",
        "KP_Prior": "rightup",
        "KP_9": "rightup",
        "KP_End": "leftdown",
        "KP_1": "leftdown",
        "KP_Next": "rightdown",
        "KP_3": "rightdown"
    }

    joystick_keys_osx = {
        524352: "fire",        # R alt
        270336: "fire",        # R control
        5374000: "fire",       # kp 0
        498073: "fire",        # kp Enter
        5963832: "up",         # kp 8
        5505074: "down",       # kp 2
        5636148: "left",       # kp 4
        5767222: "right",      # kp 6
        5832759: "leftup",     # kp 7
        6029369: "rightup",    # kp 9
        5439537: "leftdown",   # kp 1
        5570611: "rightdown",  # kp 3
    }

    joystick_keys_windows_keycode = {
        96: "fire",       # kp 0 (numlock)
        104: "up",        # kp 8 (numlock)
        98: "down",       # kp 2 (numlock)
        100: "left",      # kp 4 (numlock)
        102: "right",     # kp 6 (numlock)
        103: "leftup",    # kp 7 (numlock)
        105: "rightup",   # kp 9 (numlock)
        97: "leftdown",   # kp 1 (numlock)
        99: "rightdown"   # kp 3 (numlock)
    }

    def keyrelease(self, event):
        # first check special control keys
        if sys.platform == "darwin":
            # OSX numkeys are problematic, I try to solve this via raw keycode
            if event.keycode in self.joystick_keys_osx:
                self.screen.setjoystick(**{self.joystick_keys_osx[event.keycode]: False})
                return
        elif sys.platform == "win32":
            # Windows numkeys are also problematic, need to solve this via keysym_num OR via keycode.. (sigh)
            if event.keycode in self.joystick_keys_windows_keycode:
                self.screen.setjoystick(**{self.joystick_keys_windows_keycode[event.keycode]: False})
                return
        # sane platforms (Linux for one) play nice and just use the friendly keysym name.
        elif event.keysym in self.joystick_keys_sane_platforms:
            self.screen.setjoystick(**{self.joystick_keys_sane_platforms[event.keysym]: False})
            return

    def keypress(self, event):
        # first check special control keys
        if sys.platform == "darwin":
            # OSX numkeys are problematic, I try to solve this via raw keycode
            if event.keycode in self.joystick_keys_osx:
                self.screen.setjoystick(**{self.joystick_keys_osx[event.keycode]: True})
                return
        elif sys.platform == "win32":
            # Windows numkeys are also problematic, need to solve this via keysym_num OR via keycode.. (sigh)
            if event.keycode in self.joystick_keys_windows_keycode:
                self.screen.setjoystick(**{self.joystick_keys_windows_keycode[event.keycode]: True})
                return
        # sane platforms (Linux for one) play nice and just use the friendly keysym name.
        elif event.keysym in self.joystick_keys_sane_platforms:
            self.screen.setjoystick(**{self.joystick_keys_sane_platforms[event.keysym]: True})
            return
        # turn the event into a bit more managable key character
        char = event.char
        if not char or ord(char) > 255:
            char = event.keysym
        # print("keypress", repr(char), event.state)
        with_shift = event.state & 1
        with_control = event.state & 4
        with_alt = event.state & 8
        if char.startswith("Shift") and with_control or char.startswith("Control") and with_shift \
                or char == "??" and with_control and with_shift:
                # simulate SHIFT+COMMODORE_KEY to flip the charset
                self.screen.shifted = not self.screen.shifted
                return

        if self.interpret_thread.running_something:
            # we're running something so only the break key should do something!
            if char == '\x03' and with_control:  # ctrl+C
                self.interpret_thread.runstop()
            elif char == '\x1b':    # esc
                self.interpret_thread.runstop()
            else:
                # buffer the keypress (if it's not the pgup=RESTORE key)
                if char != 'Prior':
                    self.interpret_thread.buffer_keypress(char, event)
            return

        if len(char) == 1:
            # if '1' <= char <= '8' and self.key_control_down:
            #     self.c64screen.text = ord(char)-1
            if char == '\r':    # RETURN key
                line = self.screen.current_line(True, True, "ascii")
                line1, line2, line3 = line[0: self.columns], line[self.columns: self.columns * 2], line[self.columns * 2:]
                if line1.endswith(' '):
                    line1 = ''
                if line2.endswith(' '):
                    line3 = ''
                else:
                    line1 = ''
                line = (line1 + line2 + line3).rstrip()
                self.screen.return_key()
                if len(line) > self.columns and not line1:
                    self.screen.return_key()
                if not with_shift:
                    self.execute_direct_line(line)
            elif char in ('\x08', '\x7f', 'Delete'):
                if with_shift:
                    self.screen.insert()
                else:
                    self.screen.backspace()
            elif char == '\x03' and with_control:  # ctrl+C
                self.interpret_thread.runstop()
            elif char == '\x1b':    # esc
                self.interpret_thread.runstop()
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
            elif char == "Home":
                if with_shift:
                    self.screen.clear()
                else:
                    self.screen.cursormove(0, 0)
                self.repaint()
            elif char == "End":
                # move to end of current line
                x, y = self.screen.cursorpos()
                line = self.screen.current_line(False, True, "screencodes").rstrip()
                x = len(line)
                if x > self.columns:
                    if line[self.columns - 1] == ' ':
                        line = line[:self.columns].rstrip()
                        x = len(line)
                    else:
                        y += 1
                        x -= self.columns
                if x and x % self.columns == 0:
                    x -= 1
                self.screen.cursormove(min(x, self.columns), y)
            elif char in ("Insert", "Help"):
                self.screen.insert()
                self.repaint()
            elif char == "F7":      # directory shortcut key
                self.screen.writestr(self.interpreter.F7_dir_command + "\n")
                self.execute_direct_line(self.interpreter.F7_dir_command)
            elif char == "F5":      # load file shortcut key
                if with_shift:
                    self.screen.writestr(self.interpreter.F6_load_command + "\n")
                    self.execute_direct_line(self.interpreter.F6_load_command)
                else:
                    self.screen.writestr(self.interpreter.F5_load_command)
                    line = self.screen.current_line(False, False, "ascii")
                    self.screen.return_key()
                    self.execute_direct_line(line)
            elif char == "F3":      # run program shortcut key
                self.screen.writestr(self.interpreter.F3_run_command + "\n")
                self.execute_direct_line(self.interpreter.F3_run_command)
            elif char == "F1":      # list program shortcut key
                self.screen.writestr(self.interpreter.F1_list_command + "\n")
                self.execute_direct_line(self.interpreter.F1_list_command)
            elif char == "Prior":     # pageup = RESTORE (outside running program)
                if not self.interpret_thread.running_something:
                    self.screen.reset()
                    self.screen.memory[0x00fb] = EmulatorWindowBase.update_rate
                    self.interpreter.write_prompt("\n")

    def execute_direct_line(self, line):
        line = line.strip()
        if line.startswith("gopy"):
            self.switch_interpreter("python")
            return
        elif line.startswith((">>> go64", "go64")):
            self.switch_interpreter("basic")
            return
        self.interpret_thread.submit_line(line)

    def switch_interpreter(self, interpreter):
        if self.interpret_thread:
            self.interpret_thread.stop()
        if self.interpreter:
            self.interpreter.stop()
        self.hertztick.set()
        self.screen.reset()
        self.screen.memory[0x00fb] = EmulatorWindowBase.update_rate
        self.repaint()
        if interpreter == "basic":
            self.interpreter = BasicInterpreter(self.screen)
            self.interpret_thread = InterpretThread(self.interpreter, self)
            self.interpreter.interactive = self.interpret_thread
            self.interpreter.start()
            self.interpret_thread.start()
        elif interpreter == "python":
            self.interpreter = PythonInterpreter(self.screen)
            self.interpret_thread = InterpretThread(self.interpreter, self)
            self.interpreter.interactive = self.interpret_thread
            self.interpreter.start()
            self.interpret_thread.start()
        else:
            raise ValueError("invalid interpreter")

    def create_sprite_bitmap(self, spritenum, bitmapbytes):
        with Image.frombytes("1", (24, 21), bytes(bitmapbytes)) as si:
            si = si.resize((48, 42), 0)
            si.save(self.temp_graphics_folder + "/sprite-{:d}.xbm".format(spritenum), "xbm")
            dx = si.resize((96, 42), 0)
            dx.save(self.temp_graphics_folder + "/sprite-{:d}-2x.xbm".format(spritenum), "xbm")
            dy = si.resize((48, 84), 0)
            dy.save(self.temp_graphics_folder + "/sprite-{:d}-2y.xbm".format(spritenum), "xbm")
            dxy = si.resize((96, 84), 0)
            dxy.save(self.temp_graphics_folder + "/sprite-{:d}-2x-2y.xbm".format(spritenum), "xbm")

    def screencor_sprite(self, cc):
        # on the C-64, sprite upper left = (24, 50)
        # so subtract from regular origin (self.borderwidth, self.borderwidth) (scaled by 2 pixels)
        return cc[0] * 2 + self.bordersize - 48, cc[1] * 2 + self.bordersize - 100

    def smoothscroll(self, xs, ys):
        # c64 smooth scrolling in Y axis has offset of 3 pixels
        return -xs * 2, -(ys - 3) * 2

    def _border_positions(self):
        b1, b2, b3, b4 = super()._border_positions()
        # adjust borders for the 24 row and/or 38 column mode
        # left_xa = right_xa = top_ya = bottom_ya = 0
        if self.screen.rsel24:
            b1[3] += 8
            b2[1] += 8
            b4[1] += 8
            b3[1] -= 8
        if self.screen.csel38:
            b4[2] += 14
            b2[0] -= 18
        return b1, b2, b3, b4

    def reset_machine(self):
        super().reset_machine()
        self.screen.memory[0x00fb] = EmulatorWindowBase.update_rate
        self.switch_interpreter("basic")
        if self.screen.using_roms:
            print("using actual ROM reset routine (sys 64738)")
            do_sys(self.screen, 64738, self.interpret_thread._microsleep, use_rom_routines=True)
            self.interpreter.write_prompt("\n\n\n\n\n")


class InterpretThread(threading.Thread):
    # basic interpreter runs in a worker thread so the GUI can continue handling its events normally.
    def __init__(self, interpreter, window):
        super(InterpretThread, self).__init__(name="interpreter", daemon=True)
        self.direct_queue = queue.Queue()
        self.interpreter = interpreter
        self.interpret_lock = threading.Lock()
        self.keybuffer_lock = threading.Lock()
        self.running_program = False
        self.executing_line = False
        self.must_stop = False
        self.window = window
        self.keybuffer = deque(maxlen=16)
        self.step_counter = 0

    @property
    def running_something(self):
        return self.running_program or self.executing_line or self.interpreter.sleep_until is not None

    def run(self):
        while not self.must_stop:
            try:
                # see if we have buffered keys to be handled
                if not self.running_something:
                    with self.keybuffer_lock:
                        keyevents = list(self.keybuffer)
                        self.keybuffer.clear()
                    for when, (char, event) in enumerate(keyevents, start=1):
                        self.window.after(when, self.window.keypress(event))
                # look for work
                if self.running_program:
                    with self.interpret_lock:
                        self.interpreter.program_step()
                        self.running_program = self.interpreter.running_program
                    self.step_counter += 1
                    if self.step_counter > 200:     # control program execution speed with this
                        self.step_counter = 0
                        self._microsleep()
                    if not self.running_program:
                        self.window.screen.cursor_enabled = True
                else:
                    # check if interpreter is doing a sleep instruction
                    if self.interpreter.sleep_until is not None:
                        time_left = self.interpreter.sleep_until - time.time()
                        if time_left > 0:
                            if os.name == "nt" and time_left <= 0.016:
                                self._microsleep()    # because on Windows, sleep() takes too long
                            else:
                                time.sleep(min(0.1, time_left))
                            continue
                        self.interpreter.sleep_until = None
                        if not self.running_program:
                            self.window.screen.cursor_enabled = True
                            self.interpreter.write_prompt("\n")
                            self.executing_line = False
                            continue
                    # check for direct line commands
                    command = self.direct_queue.get()
                    if command is None:
                        break
                    self.window.screen.cursor_enabled = False
                    self.executing_line = True
                    with self.interpret_lock:
                        self.interpreter.execute_line(command)
                        self.running_program = self.interpreter.running_program
                    self._microsleep()
                    if not self.running_program and not self.interpreter.sleep_until:
                        self.window.screen.cursor_enabled = True
                    self.executing_line = False
            except ResetMachineException:
                self.stop()
                self.window.after(1, self.window.reset_machine)

    def _microsleep(self):
        # artificial microscopic delay to yield the thread and allow screen to refresh
        self.window.hertztick.wait(.02)
        self.window.hertztick.clear()

    def stop(self):
        self.interpreter.runstop()
        self.must_stop = True
        self.direct_queue.put(None)  # sentinel
        self.window.hertztick.set()
        time.sleep(0.1)

    def buffer_keypress(self, char, event):
        with self.keybuffer_lock:
            self.keybuffer.append((char, event))

    def get_bufferedkeyevent(self):
        try:
            with self.keybuffer_lock:
                return self.keybuffer.popleft()
        except IndexError:
            return (None, None)

    def do_get_command(self):
        char, event = self.get_bufferedkeyevent()
        if event:
            if len(char) == 1:
                return char
            else:
                pass  # @todo handle control characters? (F1  etc) INPUT would also need that
        return ''

    def do_sync_command(self):
        self.window.refreshtick.wait(self.window.update_rate / 1000 * 2)
        self.window.refreshtick.clear()

    def submit_line(self, line):
        self.direct_queue.put(line)

    def runstop(self):
        self.interpreter.runstop()
        with self.interpret_lock:
            if (self.executing_line or self.interpreter.sleep_until) and not self.running_program:
                self.window.screen.writestr("\n?break  error")
            if self.interpreter.sleep_until:
                self.interpreter.sleep_until = 1
            with self.keybuffer_lock:
                self.keybuffer.clear()


def start():
    rom_directory = "roms"
    screen = ScreenAndMemory(columns=C64EmulatorWindow.columns,
                             rows=C64EmulatorWindow.rows,
                             sprites=C64EmulatorWindow.sprites,
                             rom_directory=rom_directory)
    emu = C64EmulatorWindow(screen, "Commodore-64 simulator in pure Python!", rom_directory)
    emu.start()
    emu.mainloop()


if __name__ == "__main__":
    start()

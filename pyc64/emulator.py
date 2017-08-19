"""
Commodore-64 'emulator' in 100% pure Python 3.x :)

This module is the GUI window logic, handling keyboard input
and screen drawing via tkinter bitmaps.

Written by Irmen de Jong (irmen@razorvine.net)
License: MIT open-source.
"""

import io
import os
import tkinter
import pkgutil
import threading
import queue
import time
from collections import deque
from PIL import Image
from .memory import ScreenAndMemory, colorpalette
from .basic import BasicInterpreter
from .shared import ResetMachineException
from .python import PythonInterpreter


class EmulatorWindow(tkinter.Tk):
    temp_graphics_folder = "temp_gfx"
    update_rate = 1000//20    # 20 hz screen refresh rate
    columns = 40
    rows = 25
    bordersize = 64
    sprites = 8
    windowgeometry = "+200+100"
    charset_normal = "charset-normal.png"
    charset_shifted = "charset-shifted.png"

    def __init__(self, title):
        super().__init__()
        self.wm_title(title)
        self.appicon = tkinter.PhotoImage(data=pkgutil.get_data(__name__, "icon.gif"))
        self.wm_iconphoto(self, self.appicon)
        self.geometry(self.windowgeometry)
        self.hertztick = threading.Event()
        self.refreshtick = threading.Event()
        self.screen = ScreenAndMemory(columns=self.columns, rows=self.rows, sprites=self.sprites)
        self.screen.memory[0x00fb] = self.update_rate   # zero page $fb is unused, we use it for screen refresh speed setting
        self.repaint_only_dirty = True     # set to False if you're continuously changing most of the screen
        self.canvas = tkinter.Canvas(self, width=2*self.bordersize + self.columns * 16, height=2*self.bordersize + self.rows * 16, borderwidth=0, highlightthickness=0)
        self.buttonbar = tkinter.Frame(self)
        resetbut = tkinter.Button(self.buttonbar, text="reset", command=self.reset_machine)
        resetbut.pack(side=tkinter.LEFT)
        self.buttonbar.pack(fill=tkinter.X)
        topleft = self.screencor((0, 0))
        botright = self.screencor((self.columns, self.rows))
        self.screenrect = self.canvas.create_rectangle(topleft[0], topleft[1], botright[0], botright[1], outline="")
        self.spritebitmapbytes = [None] * self.sprites
        self.spritebitmaps = []
        self.create_bitmaps()
        # create the character bitmaps for all character tiles, fixed on the canvas:
        self.charbitmaps = []
        for y in range(self.rows):
            for x in range(self.columns):
                cor = self.screencor((x, y))
                bm = self.canvas.create_bitmap(cor[0], cor[1], bitmap="@"+self.temp_graphics_folder+"/char-20.xbm",
                                               foreground="black", background="white", anchor=tkinter.NW, tags="charbitmap")
                self.charbitmaps.append(bm)
        # create the sprite tkinter bitmaps:
        for i in range(self.sprites - 1, -1, -1):
            cor = self.screencor_sprite((30 + i * 20, 140 + i * 10))
            bm = self.canvas.create_bitmap(cor[0], cor[1], bitmap="@{:s}/sprite-{:d}.xbm".format(self.temp_graphics_folder, i),
                                           foreground=self.tkcolor(i+8), background=None, anchor=tkinter.NW, tags="spritebitmap")
            self.spritebitmaps.insert(0, bm)
        # the borders:
        self.border1 = self.canvas.create_rectangle(0, 0, 2*self.bordersize + self.columns * 16, self.bordersize, outline="", fill="#000")
        self.border2 = self.canvas.create_rectangle(self.bordersize + self.columns * 16, self.bordersize, 2*self.bordersize + self.columns * 16, self.bordersize + self.rows * 16, outline="", fill="#000")
        self.border3 = self.canvas.create_rectangle(0, self.bordersize + self.rows * 16, 2*self.bordersize + self.columns * 16, 2*self.bordersize + self.rows * 16, outline="", fill="#000")
        self.border4 = self.canvas.create_rectangle(0, self.bordersize, self.bordersize, self.bordersize + self.rows * 16, outline="", fill="#000")
        self.bind("<KeyPress>", lambda event: self.keypress(*self._keyevent(event)))
        self.bind("<KeyRelease>", lambda event: self.keyrelease(*self._keyevent(event)))
        self.repaint()
        self.canvas.pack()
        self._cyclic_blink_cursor()
        self._cyclic_repaint()
        self.welcome_message()
        self.interpret_thread = None
        self.interpreter = None
        self.switch_interpreter("basic")
        self.after(1000//self.screen.hz, self.hertztimer)

    def welcome_message(self):
        topleft = self.screencor((0, 0))
        introtxt = self.canvas.create_text(topleft[0] + 16 * self.columns // 2, topleft[0] + 16 * (self.rows // 2 - 2),
                                           fill="white", justify=tkinter.CENTER,
                                           text="pyc64 basic & function keys active\n\n"
                                                "use 'gopy' to enter Python mode\n\n\n\n"
                                                "(install the py64 library to be able to execute 6502 machine code)")
        self.after(4000, lambda: self.canvas.delete(introtxt))

    def hertztimer(self):
        self.after(1000//self.screen.hz, self.hertztimer)
        self.screen.hztick()
        self.hertztick.set()

    def _cyclic_blink_cursor(self):
        self.cyclic_blink_after = self.after(self.screen.cursor_blink_rate, self._cyclic_blink_cursor)
        self.screen.blink_cursor()

    def _cyclic_repaint(self):
        update_rate = max(10, self.screen.memory[0x00fb])
        self.cyclic_repaint_after = self.after(update_rate, self._cyclic_repaint)
        self.repaint()

    def _keyevent(self, event):
        c = event.char
        if not c or ord(c) > 255:
            c = event.keysym
        return c, event.state, event.x, event.y

    def keypress(self, char, state, mousex, mousey):
        # print("keypress", repr(char), state)
        with_shift = state & 1
        with_control = state & 4
        with_alt = state & 8
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
                    self.interpret_thread.buffer_keypress(char, state, mousex, mousey)
            return

        if len(char) == 1:
            # if '1' <= char <= '8' and self.key_control_down:
            #     self.c64screen.text = ord(char)-1
            if char == '\r':    # RETURN key
                line = self.screen.current_line(2)
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
            elif char == 'Home':
                if with_shift:
                    self.screen.clear()
                else:
                    self.screen.cursormove(0, 0)
                self.repaint()
            elif char in ('Insert', 'Help'):
                self.screen.insert()
                self.repaint()
            elif char == 'F7':      # directory shortcut key
                self.screen.writestr(self.interpreter.F7_dir_command + "\n")
                self.execute_direct_line(self.interpreter.F7_dir_command)
            elif char == 'F5':      # load file shortcut key
                if with_shift:
                    self.screen.writestr(self.interpreter.F6_load_command + "\n")
                    self.execute_direct_line(self.interpreter.F6_load_command)
                else:
                    self.screen.writestr(self.interpreter.F5_load_command)
                    line = self.screen.current_line(1)
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
                    self.screen.memory[0x00fb] = self.update_rate
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
        self.screen.memory[0x00fb] = self.update_rate
        self.repaint()
        self.update()
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

    def keyrelease(self, char, state, mousex, mousey):
        # print("keyrelease", repr(char), state, keycode)
        pass

    def create_bitmaps(self):
        os.makedirs(self.temp_graphics_folder, exist_ok=True)
        with open(self.temp_graphics_folder + "/readme.txt", "w") as f:
            f.write("this is a temporary folder to cache pyc64 files for tkinter graphics bitmaps.\n")
        # normal
        with Image.open(io.BytesIO(pkgutil.get_data(__name__, "charset/" + self.charset_normal))) as source_chars:
            for i in range(256):
                filename = self.temp_graphics_folder + "/char-{:02x}.xbm".format(i)
                chars = source_chars.copy()
                row, col = divmod(i, source_chars.width//16)        # we assume 16x16 pixel chars (2x zoom)
                ci = chars.crop((col * 16, row * 16, col * 16 + 16, row * 16 + 16))
                ci = ci.convert(mode="1", dither=None)
                ci.save(filename, "xbm")
        # shifted
        with Image.open(io.BytesIO(pkgutil.get_data(__name__, "charset/" + self.charset_shifted))) as source_chars:
            for i in range(256):
                filename = self.temp_graphics_folder + "/char-sh-{:02x}.xbm".format(i)
                chars = source_chars.copy()
                row, col = divmod(i, source_chars.width//16)        # we assume 16x16 pixel chars (2x zoom)
                ci = chars.crop((col * 16, row * 16, col * 16 + 16, row * 16 + 16))
                ci = ci.convert(mode="1", dither=None)
                ci.save(filename, "xbm")
        # monochrome sprites (including their double-size variants)
        sprites = self.screen.getsprites()
        for i, sprite in sprites.items():
            self.create_sprite_bitmap(i, sprite.bitmap)
            self.spritebitmapbytes[i] = sprite.bitmap

    def repaint(self):
        # set bordercolor, done by setting the 4 border rectangles
        # (screen color done by setting the background color of all character bitmaps,
        #  this is a lot faster than using many transparent bitmaps!)
        bordercolor = self.tkcolor(self.screen.border)
        if self.canvas.itemcget(self.border1, "fill") != bordercolor:
            self.canvas.itemconfigure(self.border1, fill=bordercolor)
            self.canvas.itemconfigure(self.border2, fill=bordercolor)
            self.canvas.itemconfigure(self.border3, fill=bordercolor)
            self.canvas.itemconfigure(self.border4, fill=bordercolor)
        prefix = "char-sh" if self.screen.shifted else "char"
        if self.repaint_only_dirty:
            dirty = iter(self.screen.getdirty())
        else:
            chars, colors = self.screen.getscreencopy()
            dirty = enumerate(zip(chars, colors))
        screencolor = self.tkcolor(self.screen.screen)
        for index, (char, color) in dirty:
            forecol = self.tkcolor(color)
            bm = self.charbitmaps[index]
            bitmap = "@" + self.temp_graphics_folder + "/{:s}-{:02x}.xbm".format(prefix, char)
            self.canvas.itemconfigure(bm, foreground=forecol, background=screencolor, bitmap=bitmap)
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
            self.canvas.coords(self.spritebitmaps[snum], x, y)
            if configure:
                # reconfigure all changed properties in one go
                self.canvas.itemconfigure(self.spritebitmaps[snum], **configure)
        self.refreshtick.set()

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

    def screencor(self, cc):
        return self.bordersize + cc[0] * 16, self.bordersize + cc[1] * 16

    def screencor_sprite(self, cc):
        # sprite upper left = (24, 50) so subtract from regular origin (self.borderwidth, self.borderwidth) (scaled by 2 pixels)
        return cc[0] * 2 + self.bordersize - 48, cc[1] * 2 + self.bordersize - 100

    def tkcolor(self, color):
        return "#{:06x}".format(colorpalette[color % 16])

    def reset_machine(self):
        self.screen.reset()
        self.screen.memory[0x00fb] = self.update_rate
        self.switch_interpreter("basic")
        self.repaint()


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
                        keys = list(self.keybuffer)
                        self.keybuffer.clear()
                    for when, key in enumerate(keys, start=1):
                        self.window.after(when, self.window.keypress(*key))
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
        self.window.hertztick.wait(1)
        self.window.hertztick.clear()

    def stop(self):
        self.interpreter.runstop()
        self.must_stop = True
        self.direct_queue.put(None)  # sentinel
        self.window.hertztick.set()
        time.sleep(0.1)

    def buffer_keypress(self, *params):
        with self.keybuffer_lock:
            self.keybuffer.append(params)

    def get_bufferedkey(self):
        try:
            with self.keybuffer_lock:
                return self.keybuffer.popleft()
        except IndexError:
            return None

    def do_get_command(self):
        event = self.get_bufferedkey()
        if event:
            char, state, mousex, mousey = event
            if len(char) == 1:
                return char
            else:
                pass  # @todo handle control characters? (F1  etc)
        return ''

    def do_sync_command(self):
        update_rate = max(10, self.window.screen.memory[0x00fb])
        self.window.refreshtick.wait(update_rate/1000*2)
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
    ScreenAndMemory.test_screencode_mappings()
    emu = EmulatorWindow("Commodore-64 'emulator' in pure Python!")
    emu.mainloop()


if __name__ == "__main__":
    start()

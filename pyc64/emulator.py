"""
'fast' Commodore-64 'emulator' in 100% pure Python 3.x :)

This module is the GUI window logic, handling keyboard input
and screen drawing via tkinter bitmaps.

Written by Irmen de Jong (irmen@razorvine.net)
License: MIT open-source.
"""
import sys
import os
import tkinter
import time
from PIL import Image
from .memory import ScreenAndMemory, colorpalette
from .basic import BasicInterpreter, ResetMachineException, HandleBufferedKeysException


class EmulatorWindow(tkinter.Tk):
    def __init__(self, title):
        super().__init__()
        self.wm_title(title)
        self.geometry("+200+100")
        self.screen = ScreenAndMemory()
        self.repaint_only_dirty = True     # set to False if you're continuously changing most of the screen
        self.basic = BasicInterpreter(self.screen)
        self.canvas = tkinter.Canvas(self, width=128 + 40 * 16, height=128 + 25 * 16, borderwidth=0, highlightthickness=0)
        self.buttonbar = tkinter.Frame(self)
        resetbut = tkinter.Button(self.buttonbar, text="reset", command=self.reset_machine)
        resetbut.pack(side=tkinter.LEFT)
        self.buttonbar.pack(fill=tkinter.X)
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
        self.cyclic(self.screen.blink_cursor, self.screen.cursor_blink_rate)
        self.cyclic(self.repaint, self.screen.update_rate)
        introtxt = self.canvas.create_text(topleft[0] + 320, topleft[0] + 180, text="pyc64 basic & function keys active", fill="white")
        self.after(2500, lambda: self.canvas.delete(introtxt))
        self.after(1, self.basic_interpret_loop)

    def _keyevent(self, event):
        c = event.char
        if not c or ord(c) > 255:
            c = event.keysym
        return c, event.state, event.x, event.y

    def keypress(self, char, state, mousex, mousey):
        # print("keypress", repr(char), state)  # XXX
        with_shift = state & 1
        with_control = state & 4
        with_alt = state & 8
        if char.startswith("Shift") and with_control or char.startswith("Control") and with_shift \
                or char == "??" and with_control and with_shift:
                # simulate SHIFT+COMMODORE_KEY to flip the charset
                self.screen.shifted = not self.screen.shifted
                return

        if self.basic.next_run_line_idx is not None:
            # we're running a program, only the break key should do something!
            if char == '\x03' and with_control:  # ctrl+C
                self.runstop()
            elif char == '\x1b':    # esc
                self.runstop()
            else:
                self.basic.keybuffer.append((char, state, mousex, mousey))
            return

        if len(char) == 1:
            # if '1' <= char <= '8' and self.key_control_down:
            #     self.c64screen.text = ord(char)-1
            if char == '\r':    # RETURN key
                line = self.screen.current_line(2)
                self.screen.return_key()
                if not with_shift:
                    self.screen.cursor_enabled = False
                    self.execute_direct_line(line)
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
                self.screen.writestr(dir_cmd + "\n")
                self.execute_direct_line(dir_cmd)
            elif char == 'F5':      # load file shortcut key
                if with_shift:
                    load_cmd = "load \"*\",8: "
                    self.screen.writestr(load_cmd + "\n")
                    self.execute_direct_line(load_cmd)
                else:
                    self.screen.writestr("load ")
                    x, y = self.screen.cursorpos()
                    self.screen.cursormove(x + 17, y)
                    self.screen.writestr(",8:   ")
                    line = self.screen.current_line(1)
                    self.screen.return_key()
                    self.execute_direct_line(line)
            elif char == "F3":      # run program shortcut key
                self.screen.writestr("run: \n")
                self.execute_direct_line("run")
            elif char == "F1":      # list program shortcut key
                self.screen.writestr("list: \n")
                self.execute_direct_line("list")
            elif char == "Prior":     # pageup = RESTORE (outside running program)
                if self.basic.next_run_line_idx is None:
                    self.screen.reset()
                    self.execute_direct_line("? \"\";")

    def execute_direct_line(self, line):
        try:
            self.basic.execute_line(line)
        except ResetMachineException:
            self.reset_machine()
        finally:
            pass

    def runstop(self):
        if self.basic.next_run_line_idx is not None:
            if self.basic.sleep_until:
                line = self.basic.program_lines[self.basic.next_run_line_idx - 1]
            else:
                line = self.basic.program_lines[self.basic.next_run_line_idx]
            try:
                self.basic.stop_run()
            except HandleBufferedKeysException:
                pass   # when breaking, no buffered keys will be processed
            self.screen.writestr("\nbreak in {:d}\nready.\n".format(line))
            self.screen.cursor_enabled = True

    def keyrelease(self, char, state, mousex, mousey):
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
        return "#{:06x}".format(colorpalette[color % 16])

    def cyclic(self, callable, rate, initial=True):
        if not initial:
            callable()
        self.after(rate, lambda: self.cyclic(callable, rate, False))

    def reset_machine(self):
        self.screen.reset()
        self.basic.reset()
        self.update()

    def basic_interpret_loop(self):
        self.screen.cursor_enabled = self.basic.next_run_line_idx is None
        try:
            self.basic.interpret_program_step()
        except ResetMachineException:
            self.reset_machine()
        except HandleBufferedKeysException as kx:
            key_events = kx.args[0]
            for char, state, mousex, mousey in key_events:
                self.keypress(char, state, mousex, mousey)
        # Introduce an artificial delay here, to get at least *some*
        # sense of the old times. Note that on windows it will be extremely slow somehow
        # when you time it with after_idle, so we do a workaround there.
        if sys.platform == "win32":
            self.after(1, self.basic_interpret_loop)
        else:
            time.sleep(0.0002)
            self.update_idletasks()
            self.after_idle(self.basic_interpret_loop)


def start():
    ScreenAndMemory.test_screencode_mappings()
    emu = EmulatorWindow("Fast Commodore-64 'emulator' in pure Python!")
    emu.mainloop()


if __name__ == "__main__":
    start()

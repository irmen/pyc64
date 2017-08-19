import tkinter
from pyc64.emulator import EmulatorWindow


class EmulatorPlusWindow(EmulatorWindow):
    columns = 64
    rows = 50
    bordersize = 32
    windowgeometry = "+200+40"
    sprites = 0   # for now, a larger screen will overwrite the sprite pointers so you can't use sprites. also y can not be >255

    def welcome_message(self):
        topleft = self.screencor((0, 0))
        introtxt = self.canvas.create_text(topleft[0] + 16 * self.columns // 2, topleft[0] + 16 * (self.rows // 2 - 10),
                                           fill="white", justify=tkinter.CENTER,
                                           text="WHOAAA !!!! This is what a C-64 with a 512x400 screen would look like!\n\n\n\n"
                                                "pyc64 basic & function keys active\n\n"
                                                "use 'gopy' to enter Python mode\n\n\n\n"
                                                "(install the py64 library to be able to execute 6502 machine code)")
        self.after(4000, lambda: self.canvas.delete(introtxt))


def start():
    emu = EmulatorPlusWindow("Commodore-64 \"PLUSPLUS\" 'emulator' in pure Python!")
    emu.mainloop()


if __name__ == "__main__":
    start()

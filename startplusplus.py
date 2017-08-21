import tkinter
from pyc64.emulator import EmulatorWindow


class EmulatorPlusWindow(EmulatorWindow):
    columns = 64
    rows = 50
    bordersize = 32
    windowgeometry = "+200+40"
    sprites = 0   # for now, a larger screen will overwrite the sprite pointers so you can't use sprites. also y can not be >255
    smoothscrolling = False   # tkinter is too slow to smoothly scroll a window of this size
    charset_shifted = "charset-shifted-2.png"   # define alternate charset
    colorpalette = (
        0x000000,  # 0 = black
        0xFFFFFF,  # 1 = white
        0x68372B,  # 2 = red
        0x70A4B2,  # 3 = cyan
        0x6F3D86,  # 4 = purple
        0x588D43,  # 5 = green
        0x352879,  # 6 = blue
        0xB8C76F,  # 7 = yellow
        0x6F4F25,  # 8 = orange
        0x433900,  # 9 = brown
        0x9A6759,  # 10 = light red
        0x444444,  # 11 = dark grey
        0x6C6C6C,  # 12 = medium grey
        0x9AD284,  # 13 = light green
        0x6C5EB5,  # 14 = light blue
        0x959595,  # 15 = light grey
        0x0000ff,
        0x00ff00,
        0x00ffff,
        0xff0000,
        0xff00ff,
        0xffff00,
        0x000080,
        0x008000,
        0x008080,
        0x800000,
        0x800080,
        0x808000,
        0x808080,
        0x000000,
        0x000000,
        0x000000,
    )

    def __init__(self, title):
        super(EmulatorPlusWindow, self).__init__(title)

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

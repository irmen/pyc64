import tkinter

colorpalette_morecontrast = (  # this is a palette with more contrast
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
)
colorpalette_pepto = (  # this is Pepto's Commodore-64 palette  http://www.pepto.de/projects/colorvic/
    0x000000,  # 0 = black
    0xFFFFFF,  # 1 = white
    0x813338,  # 2 = red
    0x75cec8,  # 3 = cyan
    0x8e3c97,  # 4 = purple
    0x56ac4d,  # 5 = green
    0x2e2c9b,  # 6 = blue
    0xedf171,  # 7 = yellow
    0x8e5029,  # 8 = orange
    0x553800,  # 9 = brown
    0xc46c71,  # 10 = light red
    0x4a4a4a,  # 11 = dark grey
    0x7b7b7b,  # 12 = medium grey
    0xa9ff9f,  # 13 = light green
    0x706deb,  # 14 = light blue
    0xb2b2b2,  # 15 = light grey
)
colorpalette_light = (  # this is a lighter palette
    0x000000,  # 0 = black
    0xFFFFFF,  # 1 = white
    0x984B43,  # 2 = red
    0x79C1C8,  # 3 = cyan
    0x9B51A5,  # 4 = purple
    0x68AE5C,  # 5 = green
    0x52429D,  # 6 = blue
    0xC9D684,  # 7 = yellow
    0x9B6739,  # 8 = orange
    0x6A5400,  # 9 = brown
    0xC37B75,  # 10 = light red
    0x636363,  # 11 = dark grey
    0x8A8A8A,  # 12 = medium grey
    0xA3E599,  # 13 = light green
    0x8A7BCE,  # 14 = light blue
    0xADADAD,  # 15 = light grey
)


class GUI(tkinter.Tk):
    SCALE = 3

    def __init__(self, image):
        super().__init__()
        self.colorpalette = colorpalette_pepto
        self.geometry("+200+200")
        self.title("derp")
        self.canvas = tkinter.Canvas(width=320 * self.SCALE, height=200 * self.SCALE, borderwidth=0,
                                     highlightthickness=0, xscrollincrement=1, yscrollincrement=1)
        self.canvas.pack(padx=80, pady=80)
        self.border = self.screen = 0
        self.load_image(image)
        self.after(20, self.draw_image)

    def load_image(self, image):
        img = open(image, "rb").read()
        self.img_bitmap = img[2:8002]
        self.img_screenchars = img[8002:9002]
        self.img_colorchars = img[9002:10002]
        self.img_screen = img[10002]
        self.img_border = 0
        self.border_color(self.img_border)
        self.screen_color(self.img_screen)

    def tkcolor(self, color):
        return "#{:06x}".format(self.colorpalette[color & len(self.colorpalette) - 1])

    def border_color(self, color):
        self.border = color
        self.configure(bg=self.tkcolor(color))

    def screen_color(self, color):
        self.screen = color
        self.canvas.configure(bg=self.tkcolor(color))

    def mcol_byte(self, bits, cx, cy):
        colors = [0, 0, 0, 0]
        for i in range(4):
            b = bits & 3
            bits >>= 2
            if b == 0:
                b = self.img_screen
            elif b == 1:
                b = self.img_screenchars[cx+cy*40] >> 4
            elif b == 2:
                b = self.img_screenchars[cx+cy*40] & 15
            else:
                b = self.img_colorchars[cx+cy*40]
            colors[3 - i] = b
        return colors

    def pixel(self, x, y, color):
        color = self.tkcolor(color)
        self.canvas.create_rectangle(x * self.SCALE * 2, y * self.SCALE, x * self.SCALE * 2 + self.SCALE * 2 - 1,
                                     y * self.SCALE + self.SCALE - 1, outline=color, fill=color)

    def draw_image(self):
        bi = 0
        for cy in range(25):
            for cx in range(40):
                for bb in range(8):
                    b = self.img_bitmap[bi]
                    c0, c1, c2, c3 = self.mcol_byte(b, cx, cy)
                    yy = cy*8 + bb
                    self.pixel(cx * 4, yy, c0)
                    self.pixel(cx * 4 + 1, yy, c1)
                    self.pixel(cx * 4 + 2, yy, c2)
                    self.pixel(cx * 4 + 3, yy, c3)
                    bi += 1


if __name__ == "__main__":
    gui = GUI("Image Katakis by JonEgg.koa")
    #gui = GUI("Image The Hunter by Almighty God.koa")
    #gui = GUI("Image Dinothawr Title by Arachne.koa")
    #gui = GUI("Image What Does the Fox Say by Leon.koa")
    gui.mainloop()

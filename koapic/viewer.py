import os
import tkinter
from PIL import Image, ImageTk


class ImageLoader:
    def __init__(self, filename: str) -> None:
        self.image_data = open(filename, "rb").read()

    def convert(self) -> Image:
        raise NotImplementedError("implement in subclass")


class KoalaImage(ImageLoader):
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

    def __init__(self, filename: str) -> None:
        super().__init__(filename)
        # note: first 2 bytes are the load address. Skip them.
        self.bitmap = self.image_data[2:8002]
        self.screenchars = self.image_data[8002:9002]
        self.colorchars = self.image_data[9002:10002]
        self.screen = self.image_data[10002]
        self.border = 0
        self.converted_pixels = []

    def convert(self) -> None:
        # converted = [0] * 320 * 200
        image = Image.new("P", (320, 200))
        image.putpalette(self._create_img_palette(self.colorpalette_pepto))
        bi = 0
        for cy in range(25):
            for cx in range(40):
                for bb in range(8):
                    c0, c1, c2, c3 = self._mcol_byte(self.bitmap[bi], cx, cy)
                    yy = 320 * (cy * 8 + bb)
                    # converted[cx * 8 + yy] = c0
                    # converted[cx * 8 + 1 + yy] = c0
                    # converted[cx * 8 + 2 + yy] = c1
                    # converted[cx * 8 + 3 + yy] = c1
                    # converted[cx * 8 + 4 + yy] = c2
                    # converted[cx * 8 + 5 + yy] = c2
                    # converted[cx * 8 + 6 + yy] = c3
                    # converted[cx * 8 + 7 + yy] = c3
                    yy = cy * 8 + bb
                    image.putpixel((cx * 8, yy), c0)
                    image.putpixel((cx * 8 + 1, yy), c0)
                    image.putpixel((cx * 8 + 2, yy), c1)
                    image.putpixel((cx * 8 + 3, yy), c1)
                    image.putpixel((cx * 8 + 4, yy), c2)
                    image.putpixel((cx * 8 + 5, yy), c2)
                    image.putpixel((cx * 8 + 6, yy), c3)
                    image.putpixel((cx * 8 + 7, yy), c3)
                    bi += 1
        return image.quantize(16, dither=False)

    def _create_img_palette(self, palette):
        pal = [0, 0, 0] * 256
        for i, c in enumerate(palette):
            pal[i * 3] = (c >> 16) & 255
            pal[i * 3 + 1] = (c >> 8) & 255
            pal[i * 3 + 2] = c & 255
        return pal

    def _mcol_byte(self, bits, cx, cy):
        def mcol(b):
            if b == 0:
                return self.screen & 15
            elif b == 1:
                return self.screenchars[cx + cy * 40] >> 4
            elif b == 2:
                return self.screenchars[cx + cy * 40] & 15
            else:
                return self.colorchars[cx + cy * 40] & 15

        colors = [0, 0, 0, 0]
        colors[0] = mcol(bits >> 6)
        colors[1] = mcol((bits >> 4) & 3)
        colors[2] = mcol((bits >> 2) & 3)
        colors[3] = mcol(bits & 3)
        return colors


class BitmapImage(ImageLoader):
    def convert(self) -> Image:
        header = self.image_data[:0x40]
        if header[0] != ord('B') and header[1] != ord('M'):
            raise ValueError("not a windows bitmap", header[0], header[1])
        bitmap_data_offset = header[10] + header[11] * 256 + header[12] * 256 * 256 + header[13] * 256 * 256 * 256
        dh_size = header[0x0e] + header[0x0f] * 256 + header[0x10] * 256 * 256 + header[0x11] * 256 * 256 * 256
        width = header[0x12] + header[0x13] * 256 + header[0x14] * 256 * 256 + header[0x15] * 256 * 256 * 256
        height = header[0x16] + header[0x17] * 256 + header[0x18] * 256 * 256 + header[0x19] * 256 * 256 * 256
        bits_per_pixel = header[0x1c] + header[0x1d] * 256
        # image_size = header[0x22] + header[0x23] * 256 + header[0x24] * 256 * 256 + header[0x25] * 256 * 256 * 256
        num_colors = header[0x2e] + header[0x2f] * 256 + header[0x30] * 256 * 256 + header[0x31] * 256 * 256 * 256
        if num_colors == 0:
            num_colors = 2 ** bits_per_pixel
        palette = self._create_palette(self.image_data[14+dh_size:14+dh_size + 4*num_colors])
        image = Image.new("P", (width, height))
        image.putpalette(palette)
        offset = bitmap_data_offset-0
        self.decode_image(image, self.image_data[offset:], bits_per_pixel, width, height)
        return image

    def _create_palette(self, rgba: bytes) -> bytes:
        num_colors = len(rgba)//4
        palette = []
        for i in range(num_colors):
            palette.append(rgba[i*4+2])
            palette.append(rgba[i*4+1])
            palette.append(rgba[i*4+0])
        return bytes(palette)

    def decode_image(self, image: Image, bitmap_data: bytes, bits_per_pixel: int, width: int, height: int) -> None:
        rowsize = (bits_per_pixel * width + 31) // 32 * 4
        ix = 0
        if bits_per_pixel == 8:
            for y in range(height-1, -1, -1):
                for x in range(width):
                    image.putpixel((x, y), bitmap_data[ix+x])
                ix += rowsize
        elif bits_per_pixel == 4:
            for y in range(height-1, -1, -1):
                for x in range(width//2):
                    image.putpixel((x*2, y), bitmap_data[ix+x] >> 4)
                    image.putpixel((x*2+1, y), bitmap_data[ix+x] & 15)
                ix += rowsize
        elif bits_per_pixel == 2:
            for y in range(height-1, -1, -1):
                for x in range(width//4):
                    image.putpixel((x*4, y), bitmap_data[ix+x] >> 6)
                    image.putpixel((x*4+1, y), (bitmap_data[ix+x] >> 4) & 3)
                    image.putpixel((x*4+2, y), (bitmap_data[ix+x] >> 2) & 3)
                    image.putpixel((x*4+3, y), bitmap_data[ix+x] & 3)
                ix += rowsize
        elif bits_per_pixel == 1:
            for y in range(height-1, -1, -1):
                for x in range(width//8):
                    image.putpixel((x*8, y), bitmap_data[ix+x] >> 7)
                    image.putpixel((x*8+1, y), (bitmap_data[ix+x] >> 6) & 1)
                    image.putpixel((x*8+2, y), (bitmap_data[ix+x] >> 5) & 1)
                    image.putpixel((x*8+3, y), (bitmap_data[ix+x] >> 4) & 1)
                    image.putpixel((x*8+4, y), (bitmap_data[ix+x] >> 3) & 1)
                    image.putpixel((x*8+5, y), (bitmap_data[ix+x] >> 2) & 1)
                    image.putpixel((x*8+6, y), (bitmap_data[ix+x] >> 1) & 1)
                    image.putpixel((x*8+7, y), bitmap_data[ix+x] & 1)
                ix += rowsize
        else:
            raise ValueError("bpp?", bits_per_pixel)


class PcxImage(ImageLoader):
    def convert(self) -> Image:
        header = self.image_data[:128]
        if header[0] != 0x0a:
            raise ValueError("pcx format error")
        if header[2] != 1:
            raise ValueError("pcx is not RLE-encoded")

        bits_per_pixel = header[3]
        if bits_per_pixel not in (8, 4, 1):
            raise ValueError("unsupported number of bits-per-pixel")
        if self.image_data[-769] == 12:
            rle_image = self.image_data[128:-768]
            palette = self.image_data[-768:]  # 256-color palette
        else:
            rle_image = self.image_data[128:]
            palette = self.image_data[0x10:0x40]  # 16-color palette
        minx = header[0x04] + header[0x05] * 256
        miny = header[0x06] + header[0x07] * 256
        maxx = header[0x08] + header[0x09] * 256
        maxy = header[0x0a] + header[0x0b] * 256
        width = maxx - minx + 1
        height = maxy - miny + 1
        number_of_planes = header[0x41]
        if number_of_planes != 1:
            raise ValueError("pcx has >256 colors")
        # bytes_per_line = header[0x42] + header[0x43]*256
        # palette_format = header[0x44] + header[0x45] * 256     # 0 = color/mono, 1=grayscale
        image = Image.new("P", (width, height))
        image.putpalette(palette)

        self.decode_image(image, rle_image, bits_per_pixel, width, height)
        return image

    def decode_image(self, image: Image, rle_data: bytes, bits_per_pixel: int, width: int, height: int) -> None:
        px = 0
        py = 0
        ix = 0
        if bits_per_pixel == 8:
            while py != height:
                b = rle_data[ix]
                ix += 1
                if b >> 6 == 3:
                    run_length = b & 0b00111111
                    b = rle_data[ix]
                    ix += 1
                    for _ in range(run_length):
                        image.putpixel((px, py), b)
                        px += 1
                    if px >= width:
                        px = 0
                        py += 1
                else:
                    image.putpixel((px, py), b)
                    px += 1
                    if px == width:
                        px = 0
                        py += 1
        elif bits_per_pixel == 4:
            while py != height:
                b = rle_data[ix]
                ix += 1
                if b >> 6 == 3:
                    run_length = b & 0b00111111
                    b = rle_data[ix]
                    ix += 1
                    for _ in range(run_length):
                        image.putpixel((px, py), b >> 4 & 15)
                        px += 1
                        image.putpixel((px, py), b & 15)
                        px += 1
                    if px >= width:
                        px = 0
                        py += 1
                else:
                    image.putpixel((px, py), b >> 4 & 15)
                    px += 1
                    image.putpixel((px, py), b & 15)
                    px += 1
                    if px >= width:
                        px = 0
                        py += 1
        elif bits_per_pixel == 1:
            while py != height:
                b = rle_data[ix]
                ix += 1
                if b >> 6 == 3:
                    run_length = b & 0b00111111
                    b = rle_data[ix]
                    ix += 1
                    for _ in range(run_length):
                        image.putpixel((px, py), b >> 7 & 1)
                        px += 1
                        image.putpixel((px, py), b >> 6 & 1)
                        px += 1
                        image.putpixel((px, py), b >> 5 & 1)
                        px += 1
                        image.putpixel((px, py), b >> 4 & 1)
                        px += 1
                        image.putpixel((px, py), b >> 3 & 1)
                        px += 1
                        image.putpixel((px, py), b >> 2 & 1)
                        px += 1
                        image.putpixel((px, py), b >> 1 & 1)
                        px += 1
                        image.putpixel((px, py), b & 1)
                        px += 1
                    if px >= width:
                        px = 0
                        py += 1

                else:
                    image.putpixel((px, py), b >> 7 & 1)
                    px += 1
                    image.putpixel((px, py), b >> 6 & 1)
                    px += 1
                    image.putpixel((px, py), b >> 5 & 1)
                    px += 1
                    image.putpixel((px, py), b >> 4 & 1)
                    px += 1
                    image.putpixel((px, py), b >> 3 & 1)
                    px += 1
                    image.putpixel((px, py), b >> 2 & 1)
                    px += 1
                    image.putpixel((px, py), b >> 1 & 1)
                    px += 1
                    image.putpixel((px, py), b & 1)
                    px += 1
                    if px >= width:
                        px = 0
                        py += 1

        return image


class GUI(tkinter.Tk):
    SCALE = 2

    def __init__(self):
        super().__init__()
        self.colorpalette = KoalaImage.colorpalette_light
        self.geometry("+200+200")
        self.title("C64 Koala Paint picture converter")
        self.configure(bg='black')
        self.canvas = tkinter.Canvas(width=320 * self.SCALE, height=256 * self.SCALE, bg='black', borderwidth=0,
                                     highlightthickness=0, xscrollincrement=1, yscrollincrement=1)
        self.canvas.pack(padx=20 * self.SCALE, pady=20 * self.SCALE)
        self.border = self.screen = 0

    def load_image(self, filename: str) -> None:
        if os.path.splitext(filename)[1] in (".bmp", ".BMP"):
            image = BitmapImage(filename)
        elif os.path.splitext(filename)[1] in (".pcx", ".PCX"):
            image = PcxImage(filename)
        elif os.path.splitext(filename)[1] in (".koa", ".KOA"):
            image = KoalaImage(filename)
        else:
            raise IOError("unknown image file format")
        pillow_image = image.convert()
        self.draw_image(pillow_image)

    def tkcolor(self, color):
        return "#{:06x}".format(self.colorpalette[color & len(self.colorpalette) - 1])

    def draw_image(self, image: Image) -> None:
        image = image.resize((image.size[0] * self.SCALE, image.size[1] * self.SCALE))
        self.canvas.photo_image = ImageTk.PhotoImage(image)
        self.canvas.create_image(0, 0, image=self.canvas.photo_image, anchor=tkinter.NW)
        # ci = 0
        # for y in range(200):
        #     for x in range(320):
        #         color = self.tkcolor(image.converted_pixels[ci])
        #         self.canvas.create_rectangle(x * self.SCALE, y * self.SCALE,
        #                                      x * self.SCALE + self.SCALE - 1, y * self.SCALE + self.SCALE - 1,
        #                                      outline=color, fill=color)
        #         ci += 1


if __name__ == "__main__":
    gui = GUI()
    images = [
        "nier256.bmp",
        "nier256gray.bmp",
        "nier16.bmp",
        "nier2mono.bmp",
        "test1.pcx",
        "nier256.pcx",
        "nier256gray.pcx",
        "nier2mono.pcx",
        "nier16.pcx",
        "spidey256.pcx",
        "Blubb by Sphinx.koa",
        "Dinothawr Title by Arachne.koa",
        "Bugjam 7 by JSL.koa",
        "Jazz-man by Joodas.koa",
        "Katakis by JonEgg.koa",
        "The Hunter by Almighty God.koa",
        "What Does the Fox Say by Leon.koa"]
    time = 100
    for img in images:
        gui.after(time, gui.load_image, img)
        time += 2000
    gui.mainloop()

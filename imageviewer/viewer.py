import os
import zlib
import tkinter
from typing import Tuple
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


class BmpImage(ImageLoader):
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
        palette = self._create_palette(self.image_data[14 + dh_size:14 + dh_size + 4 * num_colors])
        width_8 = (width + 7) & 0b1111111111111000
        image = Image.new("P", (width_8, height))
        image.putpalette(palette)
        offset = bitmap_data_offset - 0
        self.decode_image(image, self.image_data[offset:], bits_per_pixel, width, height)
        return image

    def _create_palette(self, rgba: bytes) -> bytes:
        num_colors = len(rgba) // 4
        palette = []
        for i in range(num_colors):
            palette.append(rgba[i * 4 + 2])
            palette.append(rgba[i * 4 + 1])
            palette.append(rgba[i * 4 + 0])
        return bytes(palette)

    def decode_image(self, image: Image, bitmap_data: bytes, bits_per_pixel: int, width: int, height: int) -> None:
        bits_width = width * bits_per_pixel
        pad_bytes = (((bits_width + 31) >> 5) << 2) - ((bits_width+7) >>3)
        ix = 0
        if bits_per_pixel == 8:
            for y in range(height - 1, -1, -1):
                for x in range(0, width, 1):
                    b = bitmap_data[ix]
                    image.putpixel((x, y), b)
                    ix += 1
                ix += pad_bytes
        elif bits_per_pixel == 4:
            for y in range(height - 1, -1, -1):
                for x in range(0, width, 2):
                    b = bitmap_data[ix]
                    image.putpixel((x, y), b >> 4)
                    image.putpixel((x + 1, y), b & 15)
                    ix += 1
                ix += pad_bytes
        elif bits_per_pixel == 2:
            for y in range(height - 1, -1, -1):
                for x in range(0, width, 4):
                    b = bitmap_data[ix]
                    image.putpixel((x, y), b >> 6)
                    image.putpixel((x + 1, y), b >> 4 & 3)
                    image.putpixel((x + 2, y), b >> 2 & 3)
                    image.putpixel((x + 3, y), b & 3)
                    ix += 1
                ix += pad_bytes
        elif bits_per_pixel == 1:
            for y in range(height - 1, -1, -1):
                for x in range(0, width, 8):
                    b = bitmap_data[ix]
                    image.putpixel((x, y), b >> 7)
                    image.putpixel((x + 1, y), b >> 6 & 1)
                    image.putpixel((x + 2, y), b >> 5 & 1)
                    image.putpixel((x + 3, y), b >> 4 & 1)
                    image.putpixel((x + 4, y), b >> 3 & 1)
                    image.putpixel((x + 5, y), b >> 2 & 1)
                    image.putpixel((x + 6, y), b >> 1 & 1)
                    image.putpixel((x + 7, y), b & 1)
                    ix += 1
                ix += pad_bytes
        else:
            raise ValueError("unsupported bpp")


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
        if width & 7:
            raise ValueError("pcx width not multiple of 8")
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


class PngImage(ImageLoader):
    def convert(self) -> Image:
        ix = 8

        def next_chunk() -> Tuple[int, bytes, bytes]:
            nonlocal ix
            chunk_size = self.image_data[ix] * 256 * 256 * 256
            ix += 1
            chunk_size |= self.image_data[ix] * 256 * 256
            ix += 1
            chunk_size |= self.image_data[ix] * 256
            ix += 1
            chunk_size |= self.image_data[ix]
            ix += 1
            chunk_type = self.image_data[ix:ix + 4]
            ix += 4
            chunk = self.image_data[ix:ix + chunk_size]
            ix += chunk_size + 4
            return chunk_size, chunk_type, chunk

        if self.image_data[:8] != b"\x89PNG\x0d\x0a\x1a\x0a":
            raise ValueError("no png image", self.image_data[:8])
        chunk_size, chunk_type, chunk = next_chunk()
        if chunk_type != b"IHDR":
            raise ValueError("IHDR missing")
        width = chunk[0] * 256 * 256 * 256 | chunk[1] * 256 * 256 | chunk[2] * 256 | chunk[3]
        height = chunk[4] * 256 * 256 * 256 | chunk[5] * 256 * 256 | chunk[6] * 256 | chunk[7]
        bit_depth = chunk[8]
        color_type = chunk[9]
        compression = chunk[10]
        filt = chunk[11]
        interlace = chunk[12]
        if interlace or filt or compression:
            raise ValueError("using interlace or filter or weird compression")
        if color_type not in (0, 3):
            raise ValueError("truecolor and/or alphachannel")
        data = b""
        width_8 = (width + 7) & 0b1111111111111000
        image = Image.new("P", (width_8, height))

        while True:
            chunk_size, chunk_type, chunk = next_chunk()
            if chunk_size == 0:
                break
            elif chunk_type == b"PLTE":
                image.putpalette(chunk)
            elif chunk_type == b"IDAT":
                data += chunk

        data = zlib.decompress(data)
        bitmap_image = []
        stride = 0

        def decode_image():
            def recon_sub(x: int, y: int) -> int:
                if x == 0:
                    return 0
                return bitmap_image[y * stride + x - 1]

            def recon_up(x: int, y: int) -> int:
                if y == 0:
                    return 0
                return bitmap_image[(y - 1) * stride + x]

            def recon_upperleft(x: int, y: int) -> int:
                if x == 0 or y == 0:
                    return 0
                return bitmap_image[(y - 1) * stride + x - 1]

            def recon_avg(x: int, y: int) -> int:
                return (recon_sub(x, y) + recon_up(x, y)) // 2

            def paeth(a: int, b: int, c: int) -> int:
                p = a + b - c
                pa = abs(p - a)
                pb = abs(p - b)
                pc = abs(p - c)
                if pa <= pb and pa <= pc:
                    pr = a
                elif pb <= pc:
                    pr = b
                else:
                    pr = c
                return pr

            ix = 0
            for y in range(height):
                filtering = data[ix]
                ix += 1
                for x in range(stride):
                    dx = data[ix]
                    ix += 1
                    if filtering == 0:
                        recon_x = dx
                    elif filtering == 1:
                        recon_x = dx + recon_sub(x, y)
                    elif filtering == 2:
                        recon_x = dx + recon_up(x, y)
                    elif filtering == 3:
                        recon_x = dx + recon_avg(x, y)
                    elif filtering == 4:
                        recon_x = dx + paeth(recon_sub(x, y), recon_up(x, y), recon_upperleft(x, y))
                    else:
                        recon_x = 0
                    bitmap_image.append(recon_x & 255)

        if bit_depth == 8:
            stride = width
            decode_image()
            for y in range(height):
                for sx in range(stride):
                    image.putpixel((sx, y), bitmap_image[sx + y * stride])
        elif bit_depth == 4:
            stride = (width+1) // 2
            decode_image()
            for y in range(height):
                for sx in range(stride):
                    b = bitmap_image[sx + y * stride]
                    x = sx*2
                    image.putpixel((x, y), b >> 4)
                    image.putpixel((x+1, y), b & 15)
        elif bit_depth == 1:
            stride = (width+7) // 8
            decode_image()
            for y in range(height):
                for sx in range(stride):
                    b = bitmap_image[sx + y * stride]
                    x = sx*8
                    image.putpixel((x, y), b >> 7 & 1)
                    image.putpixel((x+1, y), b >> 6 & 1)
                    image.putpixel((x+2, y), b >> 5 & 1)
                    image.putpixel((x+3, y), b >> 4 & 1)
                    image.putpixel((x+4, y), b >> 3 & 1)
                    image.putpixel((x+5, y), b >> 2 & 1)
                    image.putpixel((x+6, y), b >> 1 & 1)
                    image.putpixel((x+7, y), b & 1)
        else:
            raise ValueError("bit depth?", bit_depth)
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
            image = BmpImage(filename)
        elif os.path.splitext(filename)[1] in (".pcx", ".PCX"):
            image = PcxImage(filename)
        elif os.path.splitext(filename)[1] in (".koa", ".KOA"):
            image = KoalaImage(filename)
        elif os.path.splitext(filename)[1] in (".png", ".PNG"):
            image = PngImage(filename)
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
        "spideymono-oddsize.png",
        "spidey256-oddsize.png",
        "spideymono-oddsize.bmp",
        "spidey256-oddsize.bmp",
        "nier256gray.png",
        "nier16.png",
        "nier256.png",
        "nier2mono.png",
        "test1x1.pcx",
        "test1x1.bmp",
        "nier256.bmp",
        "nier256gray.bmp",
        "nier16.bmp",
        "nier2mono.bmp",
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
        "What Does the Fox Say by Leon.koa"
    ]
    time = 100
    for img in images:
        gui.after(time, gui.load_image, img)
        time += 2000
    gui.mainloop()

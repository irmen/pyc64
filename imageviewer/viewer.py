import os
import zlib
import math
import tkinter
import struct
from typing import Tuple, List
from PIL import Image, ImageTk


class ImageLoader:
    def __init__(self, filename: str) -> None:
        self.image_data = open(filename, "rb").read()

    def convert(self) -> Tuple[Image.Image, int]:
        raise NotImplementedError("implement in subclass")

    def put_eight_pixels(self, image: Image.Image, px: int, py: int, b: int) -> None:
        if b & 0b10000000:
            image.putpixel((px, py), 1)
        px += 1
        if b & 0b01000000:
            image.putpixel((px, py), 1)
        px += 1
        if b & 0b00100000:
            image.putpixel((px, py), 1)
        px += 1
        if b & 0b00010000:
            image.putpixel((px, py), 1)
        px += 1
        if b & 0b00001000:
            image.putpixel((px, py), 1)
        px += 1
        if b & 0b00000100:
            image.putpixel((px, py), 1)
        px += 1
        if b & 0b00000010:
            image.putpixel((px, py), 1)
        px += 1
        if b & 0b00000001:
            image.putpixel((px, py), 1)


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
        self.converted_pixels = []  # type: List[int]

    def convert(self) -> Tuple[Image.Image, int]:
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
        return image.quantize(16, dither=False), 16

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
    def convert(self) -> Tuple[Image.Image, int]:
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
        return image, num_colors

    def _create_palette(self, rgba: bytes) -> bytes:
        num_colors = len(rgba) // 4
        palette = []
        for i in range(num_colors):
            palette.append(rgba[i * 4 + 2])
            palette.append(rgba[i * 4 + 1])
            palette.append(rgba[i * 4 + 0])
        return bytes(palette)

    def decode_image(self, image: Image.Image, bitmap_data: bytes, bits_per_pixel: int, width: int,
                     height: int) -> None:
        bits_width = width * bits_per_pixel
        pad_bytes = (((bits_width + 31) >> 5) << 2) - ((bits_width + 7) >> 3)
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
                    self.put_eight_pixels(image, x, y, bitmap_data[ix])
                    ix += 1
                ix += pad_bytes
        else:
            raise ValueError("unsupported bpp")


class PcxImage(ImageLoader):
    def convert(self) -> Tuple[Image.Image, int]:
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
        return image, 2 ** bits_per_pixel

    def decode_image(self, image: Image.Image, rle_data: bytes, bits_per_pixel: int, width: int, height: int) -> None:
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
                        self.put_eight_pixels(image, px, py, b)
                        px += 8
                    if px >= width:
                        px = 0
                        py += 1
                else:
                    self.put_eight_pixels(image, px, py, b)
                    px += 8
                    if px >= width:
                        px = 0
                        py += 1
        return image


class PngImage(ImageLoader):
    def convert(self) -> Tuple[Image.Image, int]:
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
        bitmap_bytes = []  # type: List[int]
        stride = 0

        def decode_image():
            def recon_sub(x: int, y: int) -> int:
                if x == 0:
                    return 0
                return bitmap_bytes[y * stride + x - 1]

            def recon_up(x: int, y: int) -> int:
                if y == 0:
                    return 0
                return bitmap_bytes[(y - 1) * stride + x]

            def recon_upperleft(x: int, y: int) -> int:
                if x == 0 or y == 0:
                    return 0
                return bitmap_bytes[(y - 1) * stride + x - 1]

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
                    bitmap_bytes.append(recon_x & 255)

        def no_filtering() -> bool:
            for y in range(height):
                if data[y * (1 + stride)] != 0:
                    return False
            return True

        def decode_simple_256_color() -> Image.Image:
            # decode a 256 color indexed image that doesn't use any filtering;
            # we can write directly into the target image.
            ix = 0
            for y in range(height):
                ix += 1  # skip filter byte
                for x in range(width):
                    image.putpixel((x, y), data[ix])
                    ix += 1
            return image

        def decode_simple_16_color() -> Image.Image:
            # decode a 16 color indexed image that doesn't use any filtering;
            # we can write directly into the target image.
            ix = 0
            for y in range(height):
                ix += 1  # skip filter byte
                x = 0
                for sx in range(stride):
                    image.putpixel((x, y), data[ix] >> 4)
                    x += 1
                    image.putpixel((x, y), data[ix] & 15)
                    x += 1
                    ix += 1
            return image

        def decode_simple_2_color() -> Image.Image:
            # decode a monochrome image that doesn't use any filtering;
            # we can write directly into the target image.
            ix = 0
            for y in range(height):
                ix += 1  # skip filter byte
                x = 0
                for sx in range(stride):
                    self.put_eight_pixels(image, x, y, data[ix])
                    x += 8
                    ix += 1
            return image

        if bit_depth == 8:
            stride = width
            if no_filtering():
                return decode_simple_256_color(), 256
            decode_image()
            for y in range(height):
                for sx in range(width):
                    image.putpixel((sx, y), bitmap_bytes[sx + y * width])
        elif bit_depth == 4:
            stride = (width + 1) // 2
            if no_filtering():
                return decode_simple_16_color(), 16
            decode_image()
            for y in range(height):
                x = 0
                for sx in range(stride):
                    b = bitmap_bytes[sx + y * stride]
                    image.putpixel((x, y), b >> 4)
                    x += 1
                    image.putpixel((x, y), b & 15)
                    x += 1
        elif bit_depth == 1:
            stride = (width + 7) // 8
            if no_filtering():
                return decode_simple_2_color(), 2
            decode_image()
            for y in range(height):
                x = 0
                for sx in range(stride):
                    self.put_eight_pixels(image, x, y, bitmap_bytes[sx + y * stride])
                    x += 8
        else:
            raise ValueError("bit depth?", bit_depth)
        return image, 2 ** bit_depth


class IlbmImage(ImageLoader):
    def convert(self) -> Tuple[Image.Image, int]:
        if self.image_data[:4] != b"FORM" or self.image_data[8:12] != b"ILBM":
            raise ValueError("not an iff ilbm file")
        # size = self.image_data[4]*256*256*256 + self.image_data[5]*256*256+ self.image_data[6]*256 + self.image_data[7]
        ix = 12

        def next_chunk() -> Tuple[int, bytes, bytes]:
            nonlocal ix
            chunk_type = self.image_data[ix:ix + 4]
            ix += 4
            chunk_size = self.image_data[ix] * 256 * 256 * 256
            ix += 1
            chunk_size |= self.image_data[ix] * 256 * 256
            ix += 1
            chunk_size |= self.image_data[ix] * 256
            ix += 1
            chunk_size |= self.image_data[ix]
            ix += 1
            chunk = self.image_data[ix:ix + chunk_size]
            ix += chunk_size
            return chunk_size, chunk_type, chunk

        palette = bytearray()
        width, height = 0, 0
        num_planes = 0
        compression = 0
        self.camg = 0
        while True:
            chunk_size, chunk_type, chunk = next_chunk()
            if chunk_type == b"BMHD":
                width = chunk[0] * 256 + chunk[1]
                height = chunk[2] * 256 + chunk[3]
                num_planes = chunk[8]
                compression = chunk[10]
            elif chunk_type == b"CMAP":
                palette = bytearray(chunk)
            elif chunk_type == b"CAMG":
                self.camg = chunk[2] * 256 | chunk[3]
                if self.camg & 0x0800:
                    raise NotImplementedError("HAM mode not supported")
            elif chunk_type == b"BODY":
                if self.camg & 0x0080:
                    # extra-halfbrite mode, double the palette with half-bright colors
                    palette.extend(b"\0\0\0" * 32)
                    for i in range(32 * 3):
                        palette[i + 32 * 3] = palette[i] >> 1
                if self.camg & 0x0004:
                    # interlace, just skip every other line
                    height //= 2
                image = Image.new("P", (width, height))
                image.putpalette(palette)
                if compression:
                    self.decode_rle(image, chunk, num_planes, width, height)
                else:
                    self.decode(image, chunk, num_planes, width, height)
                return image, 2 ** num_planes

    def decode_rle(self, image: Image.Image, data: bytes, num_planes: int, width: int, height: int) -> None:
        bitplane_stride = width >> 3
        interleave_stride = bitplane_stride * num_planes
        if self.camg & 0x0004:
            # interlace, just skip every other line
            interleave_stride *= 2
        bitplane_bits = [0, 0, 0, 0, 0, 0, 0, 0]
        row_data = [0] * interleave_stride
        data_idx = 0

        def next_row():
            nonlocal data_idx, row_data
            row_idx = 0
            while row_idx < interleave_stride:
                b = data[data_idx]
                data_idx += 1
                if b > 128:
                    b2 = data[data_idx]
                    data_idx += 1
                    for _ in range(257 - b):
                        row_data[row_idx] = b2
                        row_idx += 1
                elif b < 128:
                    for _ in range(b + 1):
                        row_data[row_idx] = data[data_idx]
                        data_idx += 1
                        row_idx += 1
                else:
                    break

        for y in range(height):
            next_row()
            for x in range(width):
                bit = (x ^ 255) & 7
                bitptr = x >> 3
                for bp in range(num_planes):
                    bitplane_bits[bp] = (row_data[bitptr] >> bit) & 1
                    bitptr += bitplane_stride
                color = 0
                for bp in range(num_planes):
                    color |= bitplane_bits[bp] << bp
                image.putpixel((x, y), color)

    def decode(self, image: Image.Image, data: bytes, num_planes: int, width: int, height: int) -> None:
        bitplane_stride = width >> 3
        interleave_stride = bitplane_stride * num_planes
        if self.camg & 0x0004:
            # interlace, just skip every other line
            interleave_stride *= 2
        bitplane_bits = [0, 0, 0, 0, 0, 0, 0, 0]
        for y in range(height):
            for x in range(width):
                bit = (x ^ 255) & 7
                bitptr = y * interleave_stride + (x >> 3)
                for bp in range(num_planes):
                    bitplane_bits[bp] = (data[bitptr] >> bit) & 1
                    bitptr += bitplane_stride
                color = 0
                for bp in range(num_planes):
                    color |= bitplane_bits[bp] << bp
                image.putpixel((x, y), color)


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

    def tkcolor(self, color):
        return "#{:06x}".format(self.colorpalette[color & len(self.colorpalette) - 1])

    def draw_image(self, image: Image.Image) -> None:
        image = image.resize((image.size[0] * self.SCALE, image.size[1] * self.SCALE))
        self.canvas.delete("image")
        self.canvas.photo_image = ImageTk.PhotoImage(image)
        self.canvas.create_image(0, 0, image=self.canvas.photo_image, anchor=tkinter.NW, tag="image")
        # ci = 0
        # for y in range(200):
        #     for x in range(320):
        #         color = self.tkcolor(image.converted_pixels[ci])
        #         self.canvas.create_rectangle(x * self.SCALE, y * self.SCALE,
        #                                      x * self.SCALE + self.SCALE - 1, y * self.SCALE + self.SCALE - 1,
        #                                      outline=color, fill=color)
        #         ci += 1


class Cx16Image(ImageLoader):
    """CommanderX16 Image file format.

Numbers are encoded in little endian format (lsb first).

offset      value
-----------------
HEADER (12 bytes):
0-1    'CI' in petscii , from "CommanderX16 Image".
2      Size of the header data following this byte (currently always 9)
3-4    Width in pixels  (must be multiple of 8)
5-6    Height in pixels
7      Bits-per-pixel  (1, 2, 4 or 8)  (= 2, 4, 16 or 256 colors)
         this also determines the number of palette entries following later.
8      Settings bits.
         bit 0 and 1 = compression.  00 = uncompressed
                                     01 = PCX-RLE    [TODO not yet implemented]
                                     10 = LZSA       [TODO not yet implemented]
                                     11 = Exomizer   [TODO not yet implemented]
         bit 2 = palette format.  0 = 4 bits/channel  (2 bytes per color, $0R $GB)  [TODO not yet implemented]
                                  1 = 8 bits/channel  (3 bytes per color, $RR $GG $BB)
                4 bits per channel is the Cx16's native palette format.
         bit 3 = bitmap format.   0 = raw bitmap pixels
                                 1 = tile-based image   [TODO not yet implemented]
         bit 4 = hscale (horizontal display resulution) 0 = 320 pixels, 1 = 640 pixels
         bit 5 = vscale (vertical display resulution) 0 = 240 pixels, 1 = 480 pixels
         bit 6,7: reserved, set to 0
9-11   Size of the bitmap data following the palette data.
         This is a 24-bits number, can be 0 ("unknown", in which case just read until the end).

PALETTE (always present but size varies):
12-... Color palette. Number of entries = 2 ^ bits-per-pixel.  Number of bytes per
         entry is 2 or 3, depending on the chosen palette format in the setting bits.

BITMAPDATA (size varies):
After this, the actual image data follows.
If the bitmap format is 'raw bitmap pixels', the bimap is simply written as a sequence
of bytes making up the image's scan lines. #bytes per scan line = width * bits-per-pixel / 8
If it is 'tiles', .... [TODO]
If a compression scheme is used, the bitmap data here has to be decompressed first.
    """

    HEADER_FORMAT = "<2sBHHBBBBB"

    def __init__(self, filename=""):
        if filename:
            super().__init__(filename)
            magic, headersize, self.width, self.height, bpp, flags, bms_lsb, bms_msb, bms_hsb = \
                struct.unpack(self.HEADER_FORMAT, self.image_data[:struct.calcsize(self.HEADER_FORMAT)])
            headersize += 3
            bitmap_size = (bms_hsb << 16) | (bms_msb << 8) | bms_lsb
            if magic != b"CI":
                raise ValueError("not a Cx16 image file")
            self.num_colors = 2 ** bpp
            compression = flags & 0b00000011
            if compression != 0:
                raise NotImplementedError("no compression support yet")
            palette_format = flags & 0b00000100
            bitmap_format = flags & 0b00001000
            hscale = flags & 0b00010000
            vscale = flags & 0b00100000
            if bitmap_format == 1:
                raise NotImplementedError("tile based bitmap not yet supported")
            if palette_format == 0:
                palette_size = self.num_colors*2
                raise NotImplementedError("4 bits/channel palette not yet supported")
            else:
                palette_size = self.num_colors*3

            total_size = headersize + palette_size + bitmap_size
            if total_size != len(self.image_data):
                raise ValueError("bitmap size mismatch in header")
            self.palette = self.image_data[headersize:headersize + palette_size]
            self.image_data = self.image_data[headersize + palette_size:]
            if len(self.image_data) != self.width * self.height:
                raise ValueError("??")
        else:
            self.width = self.height = 0
            self.num_colors = 0
            self.palette = b""
            self.image_data = b""

    def load_pillow_image(self, source: Image.Image, num_colors: int) -> None:
        if source.mode != 'P':
            raise ValueError("image must be indexed colors (mode P)")
        if not (2 <= num_colors <= 256):
            raise ValueError("num colors must be between 2 and 256")
        self.width, self.height = source.size
        self.num_colors = num_colors
        self.palette = source.getpalette()[:num_colors * 3]
        self.image_data = b""
        for y in range(self.height):
            for x in range(self.width):
                self.image_data += bytes([source.getpixel((x, y))])

    def convert(self) -> Tuple[Image.Image, int]:
        image = Image.new('P', (self.width, self.height))
        image.putpalette(self.palette)
        bytedata = iter(self.image_data)
        for y in range(self.height):
            for x in range(self.width):
                image.putpixel((x, y), next(bytedata))
        return image, self.num_colors

    def write(self, filename: str) -> None:
        bits_per_pixel = int(math.log2(self.num_colors))
        if 2 ** bits_per_pixel != self.num_colors:
            raise ValueError("number of colors is not a power of 2")
        compression = 0
        bitmap_format = 0
        hscale = vscale = 0
        palette_format = 1  # 8 bits/channel = 3 bytes per color
        flags = compression | (palette_format << 2) | (bitmap_format << 3) | (hscale << 4) | (vscale << 5)
        if palette_format == 0:
            raise NotImplementedError("palette format 0  4 bits/channel not yet implemented")
        else:
            expected_palette_size = 3 * (2 ** bits_per_pixel)
            ext = b"\0\0\0" * (expected_palette_size - len(self.palette))
            palette = (bytes(self.palette) + ext)[:expected_palette_size]

        headersize = struct.calcsize(self.HEADER_FORMAT)
        bitmap_size = len(self.image_data)
        bms_lsb = bitmap_size & 255
        bms_msb = (bitmap_size >> 8) & 255
        bms_hsb = (bitmap_size >> 16) & 255
        header = struct.pack(self.HEADER_FORMAT,
                             b"CI", headersize - 3, self.width, self.height, bits_per_pixel, flags, bms_lsb, bms_msb,
                             bms_hsb)
        with open(filename, "wb") as output:
            output.write(header)
            output.write(palette)
            output.write(self.image_data)


def load_image(filename) -> ImageLoader:
    ext = os.path.splitext(filename)[1]
    if ext in (".bmp", ".BMP"):
        return BmpImage(filename)
    elif ext in (".pcx", ".PCX"):
        return PcxImage(filename)
    elif ext in (".koa", ".KOA"):
        return KoalaImage(filename)
    elif ext in (".png", ".PNG"):
        return PngImage(filename)
    elif ext in (".iff", ".IFF", ".ilbm", ".ILBM"):
        return IlbmImage(filename)
    elif ext in (".c16i", ".C16I"):
        return Cx16Image(filename)
    else:
        raise IOError("unknown image file format")


if __name__ == "__main__":

    #ci = Cx16Image("trsi-small.c16i")
    #print(ci.height, ci.width, ci.num_colors)
    #raise SystemExit

    gui = GUI()
    imagenames= ["trsi-small.c16i"]
    imagenames2 = [
        "winterqueen-ehb.iff",
        "psygnosis.iff",
        "team17.iff",
        "trsi.iff",
        "tk_truth.iff",
        "tk_truth2.iff",
        "spideymono-oddsize.png",
        "spidey256-oddsize.png",
        "nier256.png",
        "nier256gray.png",
        "nier16.png",
        "nier2mono.png",
        "trsi-small.png",
        "spideymono-oddsize.bmp",
        "spidey256-oddsize.bmp",
        "test1x1.bmp",
        "nier256.bmp",
        "nier256gray.bmp",
        "spidey256.bmp",
        "nier16.bmp",
        "nier2mono.bmp",
        "test1x1.pcx",
        "nier256.pcx",
        "nier256gray.pcx",
        "nier2mono.pcx",
        "nier16.pcx",
        "Blubb by Sphinx.koa",
        "Dinothawr Title by Arachne.koa",
        "Bugjam 7 by JSL.koa",
        "Jazz-man by Joodas.koa",
        "Katakis by JonEgg.koa",
        "The Hunter by Almighty God.koa",
        "What Does the Fox Say by Leon.koa"
    ]

    images = []
    for name in imagenames:
        pillow_image, num_colors = load_image(name).convert()
        print(name, pillow_image.size, num_colors)
        images.append(pillow_image)
        cx16image = Cx16Image()
        cx16image.load_pillow_image(pillow_image, num_colors)
        cx16image.write(os.path.splitext(name)[0] + ".c16i")

    time = 200
    for img in images:
        gui.after(time, gui.draw_image, img)
        time += 2000
    gui.mainloop()

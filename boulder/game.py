"""
Tile based screen

This module is the GUI window logic, handling keyboard input
and screen drawing via tkinter bitmaps.

Written by Irmen de Jong (irmen@razorvine.net)
License: MIT open-source.
"""

import random
import array
import io
import sys
import tkinter
import pkgutil
import threading
import time
from PIL import Image


class Tilesheet:
    def __init__(self, width, height, view_width, view_height):
        self.tiles = array.array('H', [0] * width * height)
        self.tiles_previous = array.array('H', [65535] * width * height)
        self._reset_tiles = array.array('H', self.tiles_previous)
        self.width = width
        self.height = height
        self.view_width = view_width
        self.view_height = view_height
        self.view_x = 0
        self.view_y = 0

    def set_view(self, vx, vy):
        new_vx = min(max(0, vx), self.width - self.view_width)
        new_vy = min(max(0, vy), self.height - self.view_height)
        if new_vx != self.view_x or new_vy != self.view_y:
            # the viewport has been moved, mark all tiles as dirty
            self.tiles_previous[:] = self._reset_tiles
        self.view_x = new_vx
        self.view_y = new_vy

    def __getitem__(self, xy):
        x, y = xy
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            raise ValueError("tile xy out of bounds")
        return self.tiles[x + self.width*y]

    def __setitem__(self, xy, value):
        x, y = xy
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            raise ValueError("tile xy out of bounds")
        self.tiles[x + self.width*y] = value

    def set_tiles(self, x, y, tiles):
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            raise ValueError("tile xy out of bounds")
        if type(tiles) is int:
            self.tiles[x, self.width * y] = tiles
        else:
            offset = x + self.width * y
            self.tiles[offset:offset + len(tiles)] = array.array('H', tiles)
            assert len(self.tiles) == self.width * self.height

    def dirty(self):
        # only sweep the visible part of the tilesheet (including a border of 1 tile to allow smooth scroll into view)
        diff = []
        for y in range(max(self.view_y - 1, 0), min(self.view_y + self.view_height + 1, self.height)):
            yy = self.width * y
            for x in range(max(self.view_x - 1, 0), min(self.view_x + self.view_width + 1, self.width)):
                tile = self.tiles[x + yy]
                if tile != self.tiles_previous[x + yy]:
                    diff.append((x + yy, tile))
        self.tiles_previous[:] = self.tiles
        return diff


class BoulderWindow(tkinter.Tk):
    update_rate = 1000 // 30    # 30 hz screen refresh rate
    visible_columns = 40
    visible_rows = 25
    playfield_columns = 80
    playfield_rows = 50
    scalexy = 2

    def __init__(self, title):
        super().__init__()
        if self.playfield_columns <= 0 or self.playfield_columns > 128 or self.playfield_rows <= 0 or self.playfield_rows > 128:
            raise ValueError("invalid playfield size")
        if self.visible_columns <= 0 or self.visible_columns > 128 or self.visible_rows <= 0 or self.visible_rows > 128:
            raise ValueError("invalid visible size")
        if self.scalexy not in (1, 2, 3, 4):
            raise ValueError("invalid scalexy factor")
        self.geometry("+200+40")
        self.configure(borderwidth=16, background="black")
        self.wm_title(title)
        self.appicon = tkinter.PhotoImage(data=pkgutil.get_data(__name__, "gdash_icon_48.gif"))
        self.wm_iconphoto(self, self.appicon)
        if sys.platform == "win32":
            # tell windows to use a new toolbar icon
            import ctypes
            myappid = 'net.Razorvine.Tale.story'  # arbitrary string
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        self.tilesheet = Tilesheet(self.playfield_columns, self.playfield_rows, self.visible_columns, self.visible_rows)
        self.tilesheet_score = Tilesheet(self.visible_columns, 2, self.visible_columns, 2)
        self.scorecanvas = tkinter.Canvas(self, width=self.visible_columns * 16 * self.scalexy,
                                          height=2 * 16 * self.scalexy, borderwidth=0, highlightthickness=0, background="black")
        self.canvas = tkinter.Canvas(self, width=self.visible_columns * 16 * self.scalexy,
                                     height=self.visible_rows * 16 * self.scalexy,
                                     borderwidth=0, highlightthickness=0, background="black",
                                     xscrollincrement=self.scalexy, yscrollincrement=self.scalexy)
        self.refreshtick = threading.Event()
        self.tile_images = []
        self.c_tiles = []
        self.cscore_tiles = []
        self.font_tiles_startindex = 0
        self.view_x = 0
        self.view_y = 0
        self.canvas.view_x = self.view_x
        self.canvas.view_y = self.view_y
        self.create_tile_images()
        self.create_font_tiles()
        self.bind("<KeyPress>", self.keypress)
        self.bind("<KeyRelease>", self.keyrelease)
        self.scorecanvas.pack(pady=(0, 10))
        self.canvas.pack()
        self.ticks = 0

    def start(self):
        self._cyclic_repaint()
        self._cyclic_30hz()

    def _cyclic_30hz(self):
        self.after(1000 // 30, self._cyclic_30hz)
        self.update_game()

    def _cyclic_repaint(self):
        starttime = time.perf_counter()
        self.repaint()
        self.update()
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
        for index, tile in self.tilesheet.dirty():
            img = self.canvas.itemcget(self.c_tiles[index], "image")
            if img != self.tile_images[tile]:
                self.canvas.itemconfigure(self.c_tiles[index], image=self.tile_images[tile])
        for index, tile in self.tilesheet_score.dirty():
            img = self.scorecanvas.itemcget(self.c_tiles[index], "image")
            if img != self.tile_images[tile]:
                self.scorecanvas.itemconfigure(self.cscore_tiles[index], image=self.tile_images[tile])
        # smooth scroll
        if self.canvas.view_x != self.view_x:
            self.canvas.xview_moveto(0)
            self.canvas.xview_scroll(self.view_x, tkinter.UNITS)
        if self.canvas.view_y != self.view_y:
            self.canvas.yview_moveto(0)
            self.canvas.yview_scroll(self.view_y, tkinter.UNITS)
        self.tilesheet.set_view(self.view_x // 16, self.view_y // 16)
        self.refreshtick.set()

    def create_tile_images(self):
        with Image.open(io.BytesIO(pkgutil.get_data(__name__, "boulder_rush.png"))) as tile_image:
            tile_num = 0
            while True:
                row, col = divmod(tile_num, tile_image.width // 16)       # the tileset image contains 16x16 pixel tiles
                if row * 16 > tile_image.height:
                    break
                ci = tile_image.crop((col * 16, row * 16, col * 16 + 16, row * 16 + 16))
                if self.scalexy != 1:
                    ci = ci.resize((16 * self.scalexy, 16 * self.scalexy), Image.NONE)
                out = io.BytesIO()
                ci.save(out, "png")
                img = tkinter.PhotoImage(data=out.getvalue())
                self.tile_images.append(img)
                tile_num += 1
        # create the images on the canvas for all tiles (fixed position):
        for y in range(self.playfield_rows):
            for x in range(self.playfield_columns):
                cor = self.physicalcor(self.tile2screencor((x, y)))
                tile = random.randrange(120, 127)   # stars
                self.tilesheet[x, y] = tile
                tile = self.canvas.create_image(cor[0], cor[1], image=self.tile_images[tile], anchor=tkinter.NW, tags="tile")
                self.c_tiles.append(tile)
        # create the images on the score canvas for all tiles (fixed position):
        for y in range(2):
            for x in range(self.visible_columns):
                cor = self.physicalcor(self.tile2screencor((x, y)))
                tile = random.randrange(120, 127)  # stars
                self.tilesheet_score[x, y] = tile
                tile = self.scorecanvas.create_image(cor[0], cor[1], image=self.tile_images[tile], anchor=tkinter.NW, tags="tile")
                self.cscore_tiles.append(tile)

    def create_font_tiles(self):
        self.font_tiles_startindex = len(self.tile_images)
        with Image.open(io.BytesIO(pkgutil.get_data(__name__, "font.png"))) as image:
            for c in range(0, 128):
                row, col = divmod(c, image.width // 8)       # the font image contains 8x8 pixel tiles
                if row * 8 > image.height:
                    break
                ci = image.crop((col * 8, row * 8, col * 8 + 8, row * 8 + 8))
                ci = ci.resize((16 * self.scalexy, 16 * self.scalexy), Image.NONE)
                out = io.BytesIO()
                ci.save(out, "png")
                img = tkinter.PhotoImage(data=out.getvalue())
                self.tile_images.append(img)

    def text2tiles(self, text):
        return [self.font_tiles_startindex + ord(c) for c in text]

    def tile2screencor(self, cxy):
        return cxy[0] * 16, cxy[1] * 16     # a tile is 16x16 pixels

    def physicalcor(self, sxy):
        return sxy[0] * self.scalexy, sxy[1] * self.scalexy    # the actual physical display can be a 2x2 zoom

    def tkcolor(self, color):
        return "#{:06x}".format(self.colorpalette[color & len(self.colorpalette) - 1])

    def update_game(self):
        self.ticks += 1
        self.view_x += 3
        self.view_y += 1
        self.view_x = min(max(0, self.view_x), (self.playfield_columns - self.visible_columns) * 16)
        self.view_y = min(max(0, self.view_y), (self.playfield_rows - self.visible_rows) * 16)
        for _ in range(10):
            self.tilesheet[random.randrange(0, self.playfield_columns), random.randrange(3, self.playfield_rows)] = random.randrange(1, len(self.tile_images))

        if self.ticks % 3 == 1:
            # sparkle the stars
            for i in range(len(self.tilesheet_score.tiles)):
                tile = self.tilesheet_score.tiles[i]
                if 120 <= tile <= 127:
                    tile = 120 + ((tile + 1) & 7)
                    self.tilesheet_score.tiles[i] = tile
            for i in range(len(self.tilesheet.tiles)):
                tile = self.tilesheet.tiles[i]
                if 120 <= tile <= 127:
                    tile = 120 + ((tile + 1) & 7)
                    self.tilesheet.tiles[i] = tile
            tiles = self.text2tiles("Welcome to BoulderDash!")
            self.tilesheet_score.set_tiles(4, 0, tiles)
            self.tilesheet_score.set_tiles(5, 1, tiles)


def start():
    window = BoulderWindow("Bouldertiles")
    window.start()
    window.mainloop()


if __name__ == "__main__":
    start()

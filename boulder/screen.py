"""
Tile based screen

This module is the GUI window logic, handling keyboard input
and screen drawing via tkinter bitmaps.

Written by Irmen de Jong (irmen@razorvine.net)
License: MIT open-source.
"""

import array
import io
import os
import sys
import tkinter
import pkgutil
import threading
import time
from PIL import Image


class Sprite:
    def __init__(self, name, width, height, image, canvas_item):
        self.name = name
        self.width = width
        self.height = height
        self.image = image
        self.canvas_item = canvas_item
        self.x = self.y = 0


class Playfield:
    def __init__(self, width, height, view_width, view_height):
        self.tiles = array.array('H', [1] * width * height)
        self.previously_compared_tiles = array.array('H', self.tiles)
        self.width = width
        self.height = height
        self.view_width = view_width
        self.view_height = view_height
        self.view_x = 0
        self.view_y = 0
        self.sprites = []

    def set_view(self, vx, vy):
        self.view_x = min(max(0, vx), self.width - self.view_width)
        self.view_y = min(max(0, vy), self.height - self.view_height)

    def add_sprite(self, sprite):
        self.sprites.append(sprite)

    def dirty(self):
        self.previously_compared_tiles[:] = self.tiles
        return []  # @todo
        return enumerate(self.tiles)   # @todo


class BoulderWindow(tkinter.Tk):
    temp_graphics_folder = "temp_gfx"
    update_rate = 1000 // 30    # 30 hz screen refresh rate
    visible_columns = 40
    visible_rows = 25
    playfield_columns = 80
    playfield_rows = 80
    sprites = 32
    tileset = "boulder_rush.png"

    def __init__(self, title):
        if self.playfield_columns <= 0 or self.playfield_columns > 128 or self.playfield_rows <= 0 or self.playfield_rows > 128:
            raise ValueError("invalid playfield size")
        if self.visible_columns <= 0 or self.visible_columns > 128 or self.visible_rows <= 0 or self.visible_rows > 128:
            raise ValueError("invalid visible size")
        if self.sprites < 0 or self.sprites > 256:
            raise ValueError("invalid number of sprites")
        super().__init__()
        self.geometry("+200+40")
        self.wm_title(title)
        self.appicon = tkinter.PhotoImage(data=pkgutil.get_data(__name__, "gdash_icon_48.gif"))
        self.wm_iconphoto(self, self.appicon)
        if sys.platform == "win32":
            # tell windows to use a new toolbar icon
            import ctypes
            myappid = 'net.Razorvine.Tale.story'  # arbitrary string
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        self.playfield = Playfield(self.playfield_columns, self.playfield_rows, self.visible_columns, self.visible_rows)
        self.canvas = tkinter.Canvas(self, width=self.visible_columns * 32, height=self.visible_rows * 32,
                                     borderwidth=16, highlightthickness=0, background="black", xscrollincrement=2, yscrollincrement=2)
        self.buttonbar = tkinter.Frame(self)
        resetbut = tkinter.Button(self.buttonbar, text="reset", command=self.reset_machine)
        resetbut.pack(side=tkinter.LEFT)
        self.buttonbar.pack(fill=tkinter.X)
        self.refreshtick = threading.Event()
        self.tile_images = []
        self.c_tiles = []
        self.view_x = 0
        self.view_y = 0
        self.create_tile_images()
        # create the images on the canvas for all tiles (fixed position) and the sprites (movable):
        for y in range(self.playfield_rows):
            for x in range(self.playfield_columns):
                cor = self.physicalcor(self.tile2screencor((x, y)))
                tile = self.canvas.create_image(cor[0], cor[1], image=self.tile_images[(x*y//8)%256+1], anchor=tkinter.NW, tags="tile")
                self.canvas.tag_lower(tile)
                self.c_tiles.append(tile)
        self.create_sprite_images()
        self.bind("<KeyPress>", self.keypress)
        self.bind("<KeyRelease>", self.keyrelease)
        self.canvas.pack()

    def start(self):
        self._cyclic_repaint()

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
        for index, tile in self.playfield.dirty():
            self.canvas.itemconfigure(self.c_tiles[index], image=self.tile_images[tile])
        # smooth scroll
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.canvas.xview_scroll(self.view_x, tkinter.UNITS)
        self.canvas.yview_scroll(self.view_y, tkinter.UNITS)
        self.view_x += 2
        self.view_y += 1
        self.view_x = min(max(0, self.view_x), (self.playfield_columns - self.visible_columns) * 16)
        self.view_y = min(max(0, self.view_y), (self.playfield_rows - self.visible_rows) * 16)
        self.playfield.set_view(self.view_x // 16, self.view_y // 16)
        # adjust sprite positions for smooth scroll
        for sprite in self.playfield.sprites:
            px, py = self.physicalcor((sprite.x, sprite.y))
            sx, sy = self.physicalcor((self.view_x, self.view_y))
            self.canvas.coords(sprite.canvas_item, px + sx, py + sy)
        self.refreshtick.set()

    def create_tile_images(self):
        os.makedirs(self.temp_graphics_folder, exist_ok=True)
        with open(self.temp_graphics_folder + "/readme.txt", "w") as f:
            f.write("this is a temporary folder to cache pyc64 files for tkinter graphics bitmaps.\n")
        with Image.open(io.BytesIO(pkgutil.get_data(__name__, self.tileset))) as source_chars:
            tile_num = 0
            while True:
                row, col = divmod(tile_num, source_chars.width // 16)        # we assume 16x16 pixel chars (2x zoom)
                if row * 16 > source_chars.height:
                    break
                filename = self.temp_graphics_folder + "/tile-{:04x}.png".format(tile_num)
                chars = source_chars.copy()
                ci = chars.crop((col * 16, row * 16, col * 16 + 16, row * 16 + 16))
                ci = ci.resize((32, 32), Image.NEAREST)   # double the size
                ci.save(filename, "png")
                tile_num += 1
        for i in range(tile_num):
            filename = self.temp_graphics_folder + "/tile-{:04x}.png".format(i)
            img = tkinter.PhotoImage(file=filename)
            self.tile_images.append(img)

    def create_sprite_images(self):
        data0 = pkgutil.get_data(__name__, "boulderdash_logo_sprite.png")
        image = tkinter.PhotoImage(data=data0)
        image = image.zoom(2, 2)  # double the size
        sx = 16 * self.visible_columns // 2 - image.width() // 4
        sy = 16 * self.visible_rows // 2 - image.height() // 4
        cor = self.physicalcor((sx, sy))
        cs = self.canvas.create_image(cor[0], cor[1], image=image, anchor=tkinter.NW, tags="sprite")
        self.canvas.tag_raise(cs)
        sprite = Sprite("logo", image.width(), image.height(), image, cs)
        sprite.x, sprite.y = sx, sy
        self.playfield.add_sprite(sprite)

    def tile2screencor(self, cxy):
        return cxy[0] * 16, cxy[1] * 16     # a tile is 16x16 pixels

    def physicalcor(self, sxy):
        return sxy[0] * 2, sxy[1] * 2    # the actual physical display is a 2x2 zoom

    def tkcolor(self, color):
        return "#{:06x}".format(self.colorpalette[color & len(self.colorpalette) - 1])

    def reset_machine(self):
        self.screen.reset()
        self.repaint()


def start():
    window = BoulderWindow("Bouldertiles")
    window.start()
    window.mainloop()


if __name__ == "__main__":
    start()

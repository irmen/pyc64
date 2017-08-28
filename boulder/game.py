"""
Tile based screen

This module is the GUI window logic, handling keyboard input
and screen drawing via tkinter bitmaps.

Written by Irmen de Jong (irmen@razorvine.net)
License: MIT open-source.
"""

import datetime
import random
import array
import io
import sys
import tkinter
import pkgutil
import time
from PIL import Image


class Tilesheet:
    def __init__(self, width, height, view_width, view_height):
        self.tiles = array.array('H', [0] * width * height)
        self.dirty_tiles = bytearray(width*height)
        self._dirty_clean = bytearray(width*height)
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
            self.dirty_tiles[:] = b'\x01' * self.width * self.height
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
        pos = x + self.width * y
        old_value = self.tiles[pos]
        if value != old_value:
            self.tiles[pos] = value
            self.dirty_tiles[pos] = 1

    def set_tiles(self, x, y, tiles):
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            raise ValueError("tile xy out of bounds")
        if type(tiles) is int:
            tiles = [tiles]
        for i, t in enumerate(tiles, start=x+self.width*y):
            old_value = self.tiles[i]
            if t != old_value:
                self.tiles[i] = t
                self.dirty_tiles[i] = 1

    def dirty(self):
        # return only the dirty part of the viewable area of the tilesheet
        # (including a border of 1 tile to allow smooth scroll into view)
        tiles = self.tiles
        dirty_tiles = self.dirty_tiles
        diff = []
        for y in range(max(self.view_y - 1, 0), min(self.view_y + self.view_height + 1, self.height)):
            yy = self.width * y
            for x in range(max(self.view_x - 1, 0), min(self.view_x + self.view_width + 1, self.width)):
                if dirty_tiles[x + yy]:
                    diff.append((x + yy, tiles[x + yy]))
        self.dirty_tiles[:] = self._dirty_clean
        return diff


class BoulderWindow(tkinter.Tk):
    update_fps = 20
    visible_columns = 42
    visible_rows = 22
    playfield_columns = 42
    playfield_rows = 22
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
        self.gamestate = GameState(self.tilesheet, self.update_fps)
        self.framecount_time = None
        self.framecount_frame = 0

    def start(self):
        self.framecount_time = time.perf_counter()
        self.framecount_frame = 0
        self._cyclic_repaint()

    def _cyclic_repaint(self):
        starttime = time.perf_counter()
        self.update_game()
        self.repaint()
        self.update()
        self.framecount_frame += 1
        if self.gamestate.frame % self.update_fps == 0:
            duration = time.perf_counter() - self.framecount_time
            fps = self.framecount_frame / duration
            if fps < self.update_fps:
                print("warning: FPS too low: {:.1f}".format(fps), file=sys.stderr)
            else:
                print("FPS: {:.1f}".format(fps))
            self.framecount_frame = 0
            self.framecount_time = time.perf_counter()
        duration = time.perf_counter() - starttime
        remaining_timer_budget = 1 / self.update_fps - duration
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
            self.canvas.itemconfigure(self.c_tiles[index], image=self.tile_images[tile])
        for index, tile in self.tilesheet_score.dirty():
            self.scorecanvas.itemconfigure(self.cscore_tiles[index], image=self.tile_images[tile])
        # smooth scroll
        if self.canvas.view_x != self.view_x:
            self.canvas.xview_moveto(0)
            self.canvas.xview_scroll(self.view_x, tkinter.UNITS)
        if self.canvas.view_y != self.view_y:
            self.canvas.yview_moveto(0)
            self.canvas.yview_scroll(self.view_y, tkinter.UNITS)
        self.tilesheet.set_view(self.view_x // 16, self.view_y // 16)

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
                sx, sy = self.physcoor(*self.tile2screencor(x, y))
                tile = self.canvas.create_image(sx, sy, image=self.tile_images[0], anchor=tkinter.NW, tags="tile")
                self.c_tiles.append(tile)
        # create the images on the score canvas for all tiles (fixed position):
        for y in range(2):
            for x in range(self.visible_columns):
                sx, sy = self.physcoor(*self.tile2screencor(x, y))
                self.tilesheet_score[x, y] = 0
                tile = self.scorecanvas.create_image(sx, sy, image=self.tile_images[0], anchor=tkinter.NW, tags="tile")
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

    def tile2screencor(self, cx, cy):
        return cx * 16, cy * 16     # a tile is 16x16 pixels

    def physcoor(self, sx, sy):
        return sx * self.scalexy, sy * self.scalexy    # the actual physical display can be a 2x2 zoom

    def tkcolor(self, color):
        return "#{:06x}".format(self.colorpalette[color & len(self.colorpalette) - 1])

    def scrollxypixels(self, dx, dy):
        self.view_x += dx
        self.view_y += dy
        self.view_x = min(max(0, self.view_x), (self.playfield_columns - self.visible_columns) * 16)
        self.view_y = min(max(0, self.view_y), (self.playfield_rows - self.visible_rows) * 16)

    def update_game(self):
        self.gamestate.update()
        # draw the score bar:
        tiles = self.text2tiles("\x08{lives:2d}  \x0c {keys:02d}\x7f\x7f\x7f  {diamonds:<10s}  {time:s}  $ {score:06d}".format(
            lives=self.gamestate.lives,
            time=str(self.gamestate.timeremaining)[3:7],
            score=self.gamestate.score,
            diamonds="\x0e {:02d}/{:02d}".format(self.gamestate.diamonds, self.gamestate.diamonds_needed),
            keys=self.gamestate.keys["grey"]
        ))
        self.tilesheet_score.set_tiles(1, 0, tiles)
        if self.gamestate.keys["yellow"]:
            self.tilesheet_score[10, 0] = GameState.KEY_YELLOW.spritex + GameState.KEY_YELLOW.spritey * 8
        if self.gamestate.keys["green"]:
            self.tilesheet_score[11, 0] = GameState.KEY_GREEN.spritex + GameState.KEY_GREEN.spritey * 8
        if self.gamestate.keys["red"]:
            self.tilesheet_score[12, 0] = GameState.KEY_RED.spritex + GameState.KEY_RED.spritey * 8
        tiles = self.text2tiles("Welcome to BoulderDash!")
        self.tilesheet_score.set_tiles(5, 1, tiles)


class GameObject:
    def __init__(self, rounded, explodable, consumable, spritex, spritey, sframes=0, sfps=0):
        self.rounded = rounded
        self.explodable = explodable
        self.consumable = consumable
        self.spritex = spritex
        self.spritey = spritey
        self.sframes = sframes
        self.sfps = sfps


class Cell:
    object = None       # what object is in the cell


class GameState:
    EMPTY = GameObject(False, False, True, 0, 0)
    DIRT = GameObject(False, False, True, 2, 0)
    BRICKWALL = GameObject(True, False, True, 5, 0)
    MAGICWALL = GameObject(False, False, True, 0, 23, sframes=8, sfps=20)
    PREOUTBOX = GameObject(False, False, False, 2, 6)
    OUTBOX = GameObject(False, False, False, 2, 6, sframes=2, sfps=4)
    STEELWALL = GameObject(False, False, False, 4, 0)
    FIREFLY_L = GameObject(False, True, True, 0, 17, sframes=8, sfps=20)
    FIREFLY_U = GameObject(False, True, True, 0, 17, sframes=8, sfps=20)
    FIREFLY_R = GameObject(False, True, True, 0, 17, sframes=8, sfps=20)
    FIREFLY_D = GameObject(False, True, True, 0, 17, sframes=8, sfps=20)
    BOULDER = GameObject(True, False, True, 1, 0)
    BOULDERFALLING = GameObject(False, False, True, 1, 0)
    DIAMOND = GameObject(True, False, True, 0, 31, sframes=8, sfps=20)
    DIAMONDFALLING = GameObject(False, False, True, 0, 31, sframes=8, sfps=20)
    EXPLODETOSPACE0 = GameObject(False, False, False, 0, 7)
    EXPLODETOSPACE1 = GameObject(False, False, False, 1, 7)
    EXPLODETOSPACE2 = GameObject(False, False, False, 2, 7)
    EXPLODETOSPACE3 = GameObject(False, False, False, 1, 7)
    EXPLODETOSPACE4 = GameObject(False, False, False, 0, 7)
    EXPLODETODIAMOND0 = GameObject(False, False, False, 0, 7)
    EXPLODETODIAMOND1 = GameObject(False, False, False, 1, 7)
    EXPLODETODIAMOND2 = GameObject(False, False, False, 2, 7)
    EXPLODETODIAMOND3 = GameObject(False, False, False, 3, 7)
    EXPLODETODIAMOND4 = GameObject(False, False, False, 4, 7)
    PREROCKFORD1 = GameObject(False, False, False, 6, 2, sframes=2, sfps=4)
    PREROCKFORD2 = GameObject(False, False, False, 0, 4)
    PREROCKFORD3 = GameObject(False, False, False, 1, 4)
    PREROCKFORD4 = GameObject(False, False, False, 2, 4)
    BUTTERFLY_L = GameObject(False, True, True, 0, 18, sframes=8, sfps=20)
    BUTTERFLY_U = GameObject(False, True, True, 0, 18, sframes=8, sfps=20)
    BUTTERFLY_R = GameObject(False, True, True, 0, 18, sframes=8, sfps=20)
    BUTTERFLY_D = GameObject(False, True, True, 0, 18, sframes=8, sfps=20)
    BUTTERFLY2_L = GameObject(False, True, True, 0, 19, sframes=8, sfps=20)
    BUTTERFLY2_U = GameObject(False, True, True, 0, 19, sframes=8, sfps=20)
    BUTTERFLY2_R = GameObject(False, True, True, 0, 19, sframes=8, sfps=20)
    BUTTERFLY2_D = GameObject(False, True, True, 0, 19, sframes=8, sfps=20)
    ROCKFORD = GameObject(False, True, True, 3, 4)  # standing still
    ROCKFORD.pushleft = (0, 43, 8, 20)  # pushing left
    ROCKFORD.left = (0, 28, 8, 20)  # running left
    ROCKFORD.pushright = (0, 44, 8, 20)  # pushing right
    ROCKFORD.right = (0, 29, 8, 20)  # running right
    ROCKFORD.blink = (0, 25, 8, 20)  # blinking
    ROCKFORD.tap = (0, 26, 8, 20)   # foot tapping
    ROCKFORD.blinktap = (0, 27, 8, 20)  # foot tapping and blinking
    AMOEBA = GameObject(False, False, True, 0, 25, sframes=8, sfps=20)
    STARS = GameObject(False, False, True, 0, 15, sframes=8, sfps=10)
    WATER = GameObject(False, False, True, 0, 12, sframes=8, sfps=20)
    FISH = GameObject(False, True, True, 0, 13, sframes=8, sfps=20)
    PUMPKIN = GameObject(False, True, True, 0, 14, sframes=8, sfps=20)
    BOMB = GameObject(True, False, True, 0, 6, sframes=8, sfps=10)
    AMOEBA2 = GameObject(False, False, True, 0, 24, sframes=8, sfps=20)
    DOG = GameObject(False, True, True, 0, 11, sframes=8, sfps=10)
    STEELWALL_SCROLL = GameObject(False, False, False, 0, 16, sframes=8, sfps=20)
    GHOST = GameObject(False, True, True, 0, 20, sframes=8, sfps=20)
    OMNOM = GameObject(False, True, True, 0, 21, sframes=8, sfps=20)
    BUBBLE = GameObject(False, True, True, 0, 22, sframes=8, sfps=20)
    TUMBLER = GameObject(False, True, True, 0, 37, sframes=8, sfps=10)
    JELLYFISH = GameObject(False, True, True, 0, 38, sframes=8, sfps=20)
    BOILING = GameObject(False, False, True, 0, 39, sframes=8, sfps=20)
    LEDS = GameObject(False, False, True, 0, 40, sframes=16, sfps=20)
    BAT = GameObject(False, True, True, 0, 42, sframes=8, sfps=20)
    DIAMOND2 = GameObject(True, False, True, 0, 43, sframes=8, sfps=20)
    DIAMOND2FALLING = GameObject(False, False, True, 0, 43, sframes=8, sfps=20)
    DIRT2 = GameObject(False, False, True, 3, 0)
    BOULDER2 = GameObject(True, False, True, 0, 34)
    BOULDER2FALLING = GameObject(False, False, True, 0, 34)
    DOOR_YELLOW = GameObject(False, False, False, 0, 8)
    DOOR_GREEN = GameObject(False, False, False, 1, 8)
    DOOR_RED = GameObject(False, False, False, 2, 8)
    KEY_YELLOW = GameObject(False, False, False, 3, 8)
    KEY_GREEN = GameObject(False, False, False, 4, 8)
    KEY_RED = GameObject(False, False, False, 5, 8)
    EXPLOSION0 = GameObject(False, False, False, 3, 5)
    EXPLOSION1 = GameObject(False, False, False, 4, 5)
    EXPLOSION2 = GameObject(False, False, False, 5, 5)
    EXPLOSION3 = GameObject(False, False, False, 6, 5)
    EXPLOSION4 = GameObject(False, False, False, 7, 5)

    def __init__(self, tilesheet, fps):
        self.fps = fps
        self.frame = 0
        self.lives = 9
        self.keys = {
            "grey": 0,
            "yellow": True,
            "green": True,
            "red": True
        }
        self.diamonds = 0
        self.diamonds_needed = 99
        self.score = 0
        self.time_remaining = datetime.timedelta(minutes=9, seconds=59.9999)
        self.timelimit = datetime.datetime.now() + self.time_remaining
        self.cavename = "World 1"
        self.tiles = tilesheet
        self.width = tilesheet.width
        self.height = tilesheet.height
        self.cave = []
        for _ in range(self.width * self.height):
            self.cave.append(Cell())
        self.rectangle(self.STEELWALL, 0, 0, self.tiles.width-1, self.tiles.height-1)
        self.rectangle(self.DIRT, 1, 1, self.tiles.width-2, self.tiles.height-2, fill=False)
        self.rectangle(self.DIRT2, 2, 2, self.tiles.width-3, self.tiles.height-3, fill=False)
        self.rectangle(self.BOULDER, 3, 3, self.tiles.width-4, self.tiles.height-4, fill=False)
        self.rectangle(self.BOULDER2, 4, 4, self.tiles.width-5, self.tiles.height-5, fill=False)
        self.rectangle(self.STARS, 5, 5, self.tiles.width-6, self.tiles.height-6, fill=True)

    def rectangle(self, obj, x1, y1, x2, y2, fill=False):
        self.line(obj, x1, y1, width=x2-x1+1)
        self.line(obj, x1, y2, width=x2-x1+1)
        self.line(obj, x1, y1+1, height=y2-y1-1)
        self.line(obj, x2, y1+1, height=y2-y1-1)
        if fill:
            for y in range(y1+1, y2):
                self.line(obj, x1+1, y, width=x2-x1-1)

    def line(self, obj, x, y, width=0, height=0):
        if width:
            for xx in range(x, x+width):
                self.set(xx, y, obj)
        else:
            for yy in range(y, y+height):
                self.set(x, yy, obj)

    def set(self, x, y, obj):
        self.cave[x + y*self.width].object = obj
        self.tiles[x, y] = self.select_tile(obj)

    def select_tile(self, obj):
        tile = obj.spritex + 8 * obj.spritey
        if obj.sframes:
            tile += int(obj.sfps / self.fps * self.frame) % obj.sframes
        return tile

    def get(self, x, y, direction=None):
        dirxy = {
            None: 0,
            "u": -self.width,
            "U": -self.width,
            "d": self.width,
            "D": self.width,
            "l": -1,
            "L": -1,
            "r": 1,
            "R": 1
        }
        return self.cave[x + y * self.width + dirxy[direction]].object

    def update(self):
        self.frame += 1
        self.timeremaining = self.timelimit - datetime.datetime.now()
        if self.timeremaining.seconds <= 0:
            self.timeremaining = datetime.timedelta(0)
        # sweep
        for y in range(self.height):
            for x in range(self.width):
                obj = self.get(x, y)
                if not obj:
                    continue
                if obj.sframes:
                    self.set(x, y, obj)  # mark the cell dirty to force updating its animation

        # place something randomly:
        if self.frame % 2 == 0:
            obj = random.choice([self.ROCKFORD,
                                 self.FIREFLY_L,
                                 self.MAGICWALL,
                                 self.DIAMOND,
                                 self.BUTTERFLY_L,
                                 self.BUTTERFLY2_L,
                                 self.AMOEBA,
                                 self.AMOEBA2,
                                 self.PUMPKIN,
                                 self.WATER,
                                 self.FISH,
                                 self.BOMB,
                                 self.STARS,
                                 self.DOG,
                                 self.STEELWALL_SCROLL,
                                 self.GHOST,
                                 self.OMNOM,
                                 self.BUBBLE,
                                 self.TUMBLER,
                                 self.JELLYFISH,
                                 self.BOILING,
                                 self.LEDS,
                                 self.BAT,
                                 self.DIAMOND2])
            self.set(random.randrange(1, self.tiles.width-1), random.randrange(1, self.tiles.height-1), obj)


def start():
    window = BoulderWindow("Bouldertiles")
    window.start()
    window.mainloop()


if __name__ == "__main__":
    start()

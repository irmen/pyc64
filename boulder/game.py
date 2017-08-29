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
from . import caves


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
    visible_columns = 40
    visible_rows = 22
    playfield_columns = 40
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
        pass

    def keyrelease(self, event):
        if event.keycode == 13:
            self.gamestate.next_level()

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
            keys=self.gamestate.keys["diamond"]
        ))
        self.tilesheet_score.set_tiles(0, 0, tiles)
        if self.gamestate.keys["one"]:
            self.tilesheet_score[9, 0] = GameState.KEY1.spritex + GameState.KEY1.spritey * 8
        if self.gamestate.keys["two"]:
            self.tilesheet_score[10, 0] = GameState.KEY2.spritex + GameState.KEY2.spritey * 8
        if self.gamestate.keys["three"]:
            self.tilesheet_score[11, 0] = GameState.KEY3.spritex + GameState.KEY3.spritey * 8
        tiles = self.text2tiles("Level: {:d}.{:s} (ENTER=next)                      ".format(self.gamestate.level, self.gamestate.level_name))
        self.tilesheet_score.set_tiles(0, 1, tiles[:40])


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
    # row 0
    EMPTY = GameObject(False, False, True, 0, 0)
    BOULDER = GameObject(True, False, True, 1, 0)
    DIRT = GameObject(False, False, True, 2, 0)
    DIRT2 = GameObject(False, False, True, 3, 0)
    STEEL = GameObject(False, False, False, 4, 0)
    BRICK = GameObject(True, False, True, 5, 0)
    BLADDERSPENDER = GameObject(False, False, False, 6, 0)
    VOODOO = GameObject(True, False, True, 7, 0)
    # row 1
    SWEET = GameObject(True, False, True, 0, 1)
    GRAVESTONE = GameObject(True, False, False, 1, 1)
    TRAPPEDDIAMOND = GameObject(False, False, False, 2, 1)
    DIAMONDKEY = GameObject(True, True, True, 3, 1)
    BITERSWITCH1 = GameObject(False, False, True, 4, 1)
    BITERSWITCH2 = GameObject(False, False, True, 5, 1)
    BITERSWITCH3 = GameObject(False, False, True, 6, 1)
    BITERSWITCH4 = GameObject(False, False, True, 7, 1)
    # row 2
    CLOCK = GameObject(True, False, True, 0, 2)
    CHASINGBOULDER = GameObject(True, False, True, 1, 2)
    CREATURESWITCH = GameObject(False, False, False, 2, 2)
    CREATURESWITCHON = GameObject(False, False, False, 3, 2)
    ACID = GameObject(False, False, False, 4, 2)
    SOKOBANBOX = GameObject(False, False, False, 5, 2)
    OUTBOXBLINKING = GameObject(False, False, False, 6, 2, sframes=2, sfps=4)
    OUTBOXCLOSED = GameObject(False, False, False, 6, 2)
    OUTBOXOPEN = GameObject(False, False, False, 7, 2)
    # row 3
    STEELWALLBIRTH = GameObject(False, False, False, 0, 3, sframes=4, sfps=10)
    CLOCKBIRTH = GameObject(False, False, False, 4, 3, sframes=4, sfps=10)
    # row 4
    ROCKFORDBIRTH = GameObject(False, False, False, 0, 4, sframes=4, sfps=10)
    ROCKFORD = GameObject(False, True, True, 3, 4)  # standing still
    BOULDERBIRTH = GameObject(False, False, False, 4, 4, sframes=4, sfps=10)
    # row 5
    EXPANDINGWALLSWITCHHORIZ = GameObject(False, False, False, 0, 5)
    EXPANDINGWALLSWITCHVERT = GameObject(False, False, False, 1, 5)
    ROCKFORDBOMB = GameObject(False, False, False, 2, 5)
    EXPLOSION = GameObject(False, False, False, 3, 5, sframes=5, sfps=10)
    # row 6
    BOMB = GameObject(True, False, True, 0, 6)
    IGNITEDBOMB = GameObject(True, False, True, 1, 6, sframes=7, sfps=10)
    # row 7
    DIAMONDBIRTH = GameObject(False, False, False, 0, 7, sframes=5, sfps=10)
    TELEPORTER = GameObject(False, False, False, 5, 7)
    HAMMER = GameObject(True, False, False, 6, 7)
    POT = GameObject(True, False, False, 7, 7)
    # row 8
    DOOR1 = GameObject(False, False, False, 0, 8)
    DOOR2 = GameObject(False, False, False, 1, 8)
    DOOR3 = GameObject(False, False, False, 2, 8)
    KEY1 = GameObject(False, False, False, 3, 8)
    KEY2 = GameObject(False, False, False, 4, 8)
    KEY3 = GameObject(False, False, False, 5, 8)
    # row 10
    GHOSTEXPLODE = GameObject(False, False, False, 0, 10, sframes=4, sfps=10)
    BOMBEXPLODE = GameObject(False, False, False, 4, 10, sframes=4, sfps=10)
    # row 11
    COW = GameObject(False, True, True, 0, 11, sframes=8, sfps=10)
    # row 12
    WATER = GameObject(False, False, True, 0, 12, sframes=8, sfps=20)
    # row 13
    ALTFIREFLY = GameObject(False, True, True, 0, 13, sframes=8, sfps=20)
    # row 14
    ALTBUTTERFLY = GameObject(False, True, True, 0, 14, sframes=8, sfps=20)
    # row 15
    BONUSBG = GameObject(False, False, True, 0, 15, sframes=8, sfps=10)
    # row 16
    COVERED = GameObject(False, False, False, 0, 16, sframes=8, sfps=20)
    # row 17
    FIREFLY = GameObject(False, True, True, 0, 17, sframes=8, sfps=20)
    # row 18
    BUTTERFLY = GameObject(False, True, True, 0, 18, sframes=8, sfps=20)
    # row 19
    STONEFLY = GameObject(False, True, True, 0, 19, sframes=8, sfps=20)
    # row 20
    GHOST = GameObject(False, True, True, 0, 20, sframes=8, sfps=20)
    # row 21
    BITER = GameObject(False, True, True, 0, 21, sframes=8, sfps=20)
    # row 22
    BLADDER = GameObject(False, True, True, 0, 22, sframes=8, sfps=20)
    # row 23
    MAGICWALL = GameObject(False, False, True, 0, 23, sframes=8, sfps=20)
    # row 24
    AMOEBA = GameObject(False, False, True, 0, 24, sframes=8, sfps=20)
    # row 25
    SLIME = GameObject(False, False, True, 0, 25, sframes=8, sfps=20)
    # row 26 - 30
    ROCKFORDBLINK = GameObject(False, True, True, 0, 26, sframes=8, sfps=20)
    ROCKFORDTAP = GameObject(False, True, True, 0, 27, sframes=8, sfps=20)
    ROCKFORDTAPBLINK = GameObject(False, True, True, 0, 28, sframes=8, sfps=20)
    ROCKFORDLEFT = GameObject(False, True, True, 0, 29, sframes=8, sfps=20)
    ROCKFORDRIGHT = GameObject(False, True, True, 0, 30, sframes=8, sfps=20)
    # row 31
    DIAMOND = GameObject(True, False, True, 0, 31, sframes=8, sfps=20)
    # row 32
    ROCKFORDSTIRRING = GameObject(False, True, True, 0, 32, sframes=8, sfps=20)
    # row 33   @todo hammer
    # row 34
    MEGABOULDER = GameObject(True, False, True, 0, 34)
    SKELETON = GameObject(True, False, True, 1, 34)
    GRAVITYSWITCH = GameObject(False, False, False, 2, 34)
    GRAVITYSWITCHON = GameObject(False, False, False, 3, 34)
    WALLSLOPEDUPRIGHT = GameObject(True, False, True, 4, 34)
    WALLSLOPEDUPLEFT = GameObject(True, False, True, 5, 34)
    WALLSLOPEDDOWNLEFT = GameObject(True, False, True, 6, 34)
    WALLSLOPEDDOWNRIGHT = GameObject(True, False, True, 7, 34)
    # row 35
    DIRTSLOPEDUPRIGHT = GameObject(True, False, True, 0, 35)
    DIRTSLOPEDUPLEFT = GameObject(True, False, True, 1, 35)
    DIRTSLOPEDDOWNLEFT = GameObject(True, False, True, 2, 35)
    DIRTSLOPEDDOWNRIGHT = GameObject(True, False, True, 3, 35)
    STEELWALLSLOPEDUPRIGHT = GameObject(True, False, True, 4, 35)
    STEELWALLSLOPEDUPLEFT = GameObject(True, False, True, 5, 35)
    STEELWALLSLOPEDDOWNLEFT = GameObject(True, False, True, 6, 35)
    STEELWALLSLOPEDDOWNRIGHT = GameObject(True, False, True, 7, 35)
    # row 36
    NITROFLASK = GameObject(True, False, True, 0, 36)
    DIRTBALL = GameObject(True, False, True, 1, 36)
    REPLICATORSWITCHON = GameObject(False, False, False, 2, 36)
    REPLICATORSWITCHOFF = GameObject(False, False, False, 3, 36)
    AMOEBAEXPLODE = GameObject(False, False, False, 4, 36, sframes=4, sfps=10)
    # row 37
    AMOEBARECTANGLE = GameObject(False, True, True, 0, 37, sframes=8, sfps=10)
    # row 38
    REPLICATOR = GameObject(False, False, False, 0, 38, sframes=8, sfps=20)
    # row 39
    LAVA = GameObject(False, False, True, 0, 39, sframes=8, sfps=20)
    # row 40
    CONVEYORRIGHT = GameObject(False, False, True, 0, 40, sframes=8, sfps=20)
    # row 41
    CONVEYORLEFT = GameObject(False, False, True, 0, 41, sframes=8, sfps=20)
    # row 42
    DRAGONFLY = GameObject(False, True, True, 0, 42, sframes=8, sfps=20)
    # row 43
    FLYINGDIAMOND = GameObject(True, False, True, 0, 43, sframes=8, sfps=20)
    # row 44
    DIRTLOOSE = GameObject(False, False, True, 0, 44)
    CONVEYORDIRECTIONSWITCHNORMAL = GameObject(False, False, False, 1, 44)
    CONVEYORDIRECTIONSWITCHCHANGED = GameObject(False, False, False, 2, 44)
    CONVEYORDIRECTIONSWITCHOFF = GameObject(False, False, False, 3, 44)
    CONVEYORDIRECTIONSWITCHON = GameObject(False, False, False, 4, 44)
    FLYINGBOULDER = GameObject(False, True, True, 5, 44)
    COCONUT = GameObject(False, False, True, 6, 44)
    # row 45
    NUTCRACK = GameObject(False, False, False, 0, 45, sframes=4, sfps=10)
    ROCKETRIGHT = GameObject(False, False, True, 4, 45)
    ROCKETUP = GameObject(False, False, True, 5, 45)
    ROCKETLEFT = GameObject(False, False, True, 6, 45)
    ROCKETDOWN = GameObject(False, False, True, 7, 45)
    # row 46
    ROCKETLAUNCHER = GameObject(False, False, True, 0, 46)
    ROCKFORDROCKETLAUNCHER = GameObject(False, True, True, 1, 46)
    # row 49 - 50
    ROCKFORDPUSHLEFT = GameObject(False, True, True, 0, 49, sframes=8, sfps=20)
    ROCKFORDPUSHRIGHT = GameObject(False, True, True, 0, 50, sframes=8, sfps=20)

    def __init__(self, tilesheet, fps):
        self.level = 1
        self.fps = fps
        self.frame = 0
        self.lives = 9
        self.keys = {
            "diamond": 0,
            "one": True,
            "two": True,
            "three": True
        }
        self.diamonds = 0
        self.score = 0
        self.tiles = tilesheet
        self.width = tilesheet.width
        self.height = tilesheet.height
        self.cave = []
        self.level_name = "???"
        for _ in range(self.width * self.height):
            self.cave.append(Cell())
        self.load_c64level()

    def load_c64level(self):
        c64cave = caves.Cave.decode_from_lvl(self.level)
        assert c64cave.width == self.tiles.width and c64cave.height == self.tiles.height
        self.level_name = c64cave.name
        self.diamonds_needed = c64cave.diamonds_needed
        self.time_remaining = datetime.timedelta(seconds=c64cave.time)
        self.timelimit = datetime.datetime.now() + self.time_remaining
        # convert the c64 cave map
        conversion = {
            0x00: self.EMPTY,
            0x01: self.DIRT,
            0x02: self.BRICK,
            0x03: self.MAGICWALL,
            0x04: self.OUTBOXCLOSED,
            0x05: self.OUTBOXBLINKING,
            0x07: self.STEEL,
            0x08: self.FIREFLY,
            0x09: self.FIREFLY,
            0x0a: self.FIREFLY,
            0x0b: self.FIREFLY,
            0x10: self.BOULDER,
            0x12: self.BOULDER,
            0x14: self.DIAMOND,
            0x16: self.DIAMOND,
            0x25: self.ROCKFORDBIRTH,
            0x30: self.BUTTERFLY,
            0x31: self.BUTTERFLY,
            0x32: self.BUTTERFLY,
            0x33: self.BUTTERFLY,
            0x38: self.ROCKFORD,
            0x3a: self.AMOEBA
        }
        for i, obj in enumerate(c64cave.map):
            y, x = divmod(i, self.width)
            self.draw_single(conversion[obj], x, y)

    def draw_rectangle(self, obj, x1, y1, width, height, fillobject=None):
        self.draw_line(obj, x1, y1, width, 'r')
        self.draw_line(obj, x1, y1 + height - 1, width, 'r')
        self.draw_line(obj, x1, y1 + 1, height - 2, 'd')
        self.draw_line(obj, x1 + width - 1, y1 + 1, height - 2, 'd')
        if fillobject is not None:
            for y in range(y1+1, y1+height - 1):
                self.draw_line(fillobject, x1 + 1, y, width-2, 'r')

    def draw_line(self, obj, x, y, length, direction):
        dx, dy = {
            "l": (-1, 0),
            "r": (1, 0),
            "u": (0, -1),
            "d": (0, 1),
            "lu": (-1, -1),
            "ru": (1, -1),
            "ld": (-1, 1),
            "rd": (1, 1)
        }[direction.lower()]
        for _ in range(length):
            self.draw_single(obj, x, y)
            x += dx
            y += dy

    def draw_single(self, obj, x, y):
        self.cave[x + y*self.width].object = obj
        self.tiles[x, y] = self.select_tile(obj)

    def select_tile(self, obj):
        # select the tile to display (also for animated objects)
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

    def next_level(self):
        self.level = (self.level % len(caves.CAVES)) + 1
        self.load_c64level()

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
                    self.draw_single(obj, x, y)  # mark the cell dirty to force updating its animation

        # place something randomly:
        # if self.frame % 20 == 19:
        #     obj = random.choice([self.ROCKFORDBLINK,
        #                          self.ROCKFORDTAP,
        #                          self.ROCKFORDTAPBLINK,
        #                          self.ROCKFORDLEFT,
        #                          self.ROCKFORDRIGHT,
        #                          self.ROCKFORDPUSHLEFT,
        #                          self.ROCKFORDPUSHRIGHT,
        #                          self.EXPLOSION,
        #                          self.FIREFLY,
        #                          self.BUTTERFLY,
        #                          self.STONEFLY,
        #                          self.AMOEBA,
        #                          self.ALTBUTTERFLY,
        #                          self.ALTFIREFLY,
        #                          self.COW,
        #                          self.GHOST,
        #                          self.BITER,
        #                          self.BLADDER,
        #                          self.AMOEBARECTANGLE,
        #                          self.DRAGONFLY,
        #                          self.MAGICWALL,
        #                          self.DIAMOND,
        #                          self.FLYINGDIAMOND,
        #                          self.WATER,
        #                          self.REPLICATOR,
        #                          self.BOMB,
        #                          self.BOMBEXPLODE,
        #                          self.BONUSBG,
        #                          self.COVERED,
        #                          self.REPLICATOR,
        #                          self.LAVA,
        #                          self.IGNITEDBOMB])
        #     self.draw_single(obj, random.randrange(1, self.tiles.width - 1), random.randrange(1, self.tiles.height - 1))


def start():
    window = BoulderWindow("Bouldertiles")
    window.start()
    window.mainloop()


if __name__ == "__main__":
    start()

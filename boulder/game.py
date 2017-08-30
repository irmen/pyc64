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
        self.dirty_tiles = bytearray(width * height)
        self._dirty_clean = bytearray(width * height)
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
        return self.tiles[x + self.width * y]

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
        for i, t in enumerate(tiles, start=x + self.width * y):
            old_value = self.tiles[i]
            if t != old_value:
                self.tiles[i] = t
                self.dirty_tiles[i] = 1

    def set_dirty(self, x, y):
        self.dirty_tiles[x + y * self.width] = True

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
    update_fps = 30
    update_timestep = 1 / update_fps
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
        self.tile_image_numcolumns = 0
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
        self.gamestate = GameState(self.tilesheet, self.update_fps, self.tile_image_numcolumns)
        self.gfxupdate_starttime = None
        self.game_update_dt = None
        self.graphics_update_dt = None
        self.graphics_frame = 0

    def start(self):
        self.gfxupdate_starttime = time.perf_counter()
        self.game_update_dt = 0.0
        self.graphics_update_dt = 0.0
        self.graphics_frame = 0
        self.tick_loop()

    def tick_loop(self):
        now = time.perf_counter()
        dt = now - self.gfxupdate_starttime
        self.game_update_dt += dt
        while self.game_update_dt > self.gamestate.update_timestep:
            self.game_update_dt -= self.gamestate.update_timestep
            self.update_game()
        self.graphics_update_dt += dt
        if self.graphics_update_dt > self.update_timestep:
            self.graphics_update_dt -= self.update_timestep
            if self.graphics_update_dt >= self.update_timestep:
                print("Gfx update too slow to reach {:d} fps!".format(self.update_fps))
            self.repaint()
        self.gfxupdate_starttime = now
        self.after(1000 // 120, self.tick_loop)

    def keypress(self, event):
        pass

    def keyrelease(self, event):
        if event.keysym == "Return":
            self.gamestate.next_level()

    def repaint(self):
        # for all tiles that have sprite animation, update to the next animation image
        self.graphics_frame += 1
        animtiles = self.gamestate.tiles_with_animations()
        for at in animtiles:
            obj = at.obj
            tile = obj.spritex + self.tile_image_numcolumns * obj.spritey + int(obj.sfps / self.update_fps * self.graphics_frame) % obj.sframes
            self.tilesheet[at.x, at.y] = tile
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
            self.tile_image_numcolumns = tile_image.width // 16      # the tileset image contains 16x16 pixel tiles
            while True:
                row, col = divmod(tile_num, self.tile_image_numcolumns)
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
            self.tilesheet_score[9, 0] = GameObject.KEY1.spritex + GameObject.KEY1.spritey * self.tile_image_numcolumns
        if self.gamestate.keys["two"]:
            self.tilesheet_score[10, 0] = GameObject.KEY2.spritex + GameObject.KEY2.spritey * self.tile_image_numcolumns
        if self.gamestate.keys["three"]:
            self.tilesheet_score[11, 0] = GameObject.KEY3.spritex + GameObject.KEY3.spritey * self.tile_image_numcolumns
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

# row 0
GameObject.EMPTY = GameObject(False, False, True, 0, 0)
GameObject.BOULDER = GameObject(True, False, True, 1, 0)
GameObject.DIRT = GameObject(False, False, True, 2, 0)
GameObject.DIRT2 = GameObject(False, False, True, 3, 0)
GameObject.STEEL = GameObject(False, False, False, 4, 0)
GameObject.BRICK = GameObject(True, False, True, 5, 0)
GameObject.BLADDERSPENDER = GameObject(False, False, False, 6, 0)
GameObject.VOODOO = GameObject(True, False, True, 7, 0)
# row 1
GameObject.SWEET = GameObject(True, False, True, 0, 1)
GameObject.GRAVESTONE = GameObject(True, False, False, 1, 1)
GameObject.TRAPPEDDIAMOND = GameObject(False, False, False, 2, 1)
GameObject.DIAMONDKEY = GameObject(True, True, True, 3, 1)
GameObject.BITERSWITCH1 = GameObject(False, False, True, 4, 1)
GameObject.BITERSWITCH2 = GameObject(False, False, True, 5, 1)
GameObject.BITERSWITCH3 = GameObject(False, False, True, 6, 1)
GameObject.BITERSWITCH4 = GameObject(False, False, True, 7, 1)
# row 2
GameObject.CLOCK = GameObject(True, False, True, 0, 2)
GameObject.CHASINGBOULDER = GameObject(True, False, True, 1, 2)
GameObject.CREATURESWITCH = GameObject(False, False, False, 2, 2)
GameObject.CREATURESWITCHON = GameObject(False, False, False, 3, 2)
GameObject.ACID = GameObject(False, False, False, 4, 2)
GameObject.SOKOBANBOX = GameObject(False, False, False, 5, 2)
GameObject.OUTBOXBLINKING = GameObject(False, False, False, 6, 2, sframes=2, sfps=4)
GameObject.OUTBOXCLOSED = GameObject(False, False, False, 6, 2)
GameObject.OUTBOXOPEN = GameObject(False, False, False, 7, 2)
# row 3
GameObject.STEELWALLBIRTH = GameObject(False, False, False, 0, 3, sframes=4, sfps=10)
GameObject.CLOCKBIRTH = GameObject(False, False, False, 4, 3, sframes=4, sfps=10)
# row 4
GameObject.ROCKFORDBIRTH = GameObject(False, False, False, 0, 4, sframes=4, sfps=10)
GameObject.ROCKFORD = GameObject(False, True, True, 3, 4)  # standing still
GameObject.BOULDERBIRTH = GameObject(False, False, False, 4, 4, sframes=4, sfps=10)
# row 5
GameObject.EXPANDINGWALLSWITCHHORIZ = GameObject(False, False, False, 0, 5)
GameObject.EXPANDINGWALLSWITCHVERT = GameObject(False, False, False, 1, 5)
GameObject.ROCKFORDBOMB = GameObject(False, False, False, 2, 5)
GameObject.EXPLOSION = GameObject(False, False, False, 3, 5, sframes=5, sfps=10)
# row 6
GameObject.BOMB = GameObject(True, False, True, 0, 6)
GameObject.IGNITEDBOMB = GameObject(True, False, True, 1, 6, sframes=7, sfps=10)
# row 7
GameObject.DIAMONDBIRTH = GameObject(False, False, False, 0, 7, sframes=5, sfps=10)
GameObject.TELEPORTER = GameObject(False, False, False, 5, 7)
GameObject.HAMMER = GameObject(True, False, False, 6, 7)
GameObject.POT = GameObject(True, False, False, 7, 7)
# row 8
GameObject.DOOR1 = GameObject(False, False, False, 0, 8)
GameObject.DOOR2 = GameObject(False, False, False, 1, 8)
GameObject.DOOR3 = GameObject(False, False, False, 2, 8)
GameObject.KEY1 = GameObject(False, False, False, 3, 8)
GameObject.KEY2 = GameObject(False, False, False, 4, 8)
GameObject.KEY3 = GameObject(False, False, False, 5, 8)
# row 10
GameObject.GHOSTEXPLODE = GameObject(False, False, False, 0, 10, sframes=4, sfps=10)
GameObject.BOMBEXPLODE = GameObject(False, False, False, 4, 10, sframes=4, sfps=10)
# row 11
GameObject.COW = GameObject(False, True, True, 0, 11, sframes=8, sfps=10)
# row 12
GameObject.WATER = GameObject(False, False, True, 0, 12, sframes=8, sfps=20)
# row 13
GameObject.ALTFIREFLY = GameObject(False, True, True, 0, 13, sframes=8, sfps=20)
# row 14
GameObject.ALTBUTTERFLY = GameObject(False, True, True, 0, 14, sframes=8, sfps=20)
# row 15
GameObject.BONUSBG = GameObject(False, False, True, 0, 15, sframes=8, sfps=10)
# row 16
GameObject.COVERED = GameObject(False, False, False, 0, 16, sframes=8, sfps=20)
# row 17
GameObject.FIREFLY = GameObject(False, True, True, 0, 17, sframes=8, sfps=20)
# row 18
GameObject.BUTTERFLY = GameObject(False, True, True, 0, 18, sframes=8, sfps=20)
# row 19
GameObject.STONEFLY = GameObject(False, True, True, 0, 19, sframes=8, sfps=20)
# row 20
GameObject.GHOST = GameObject(False, True, True, 0, 20, sframes=8, sfps=20)
# row 21
GameObject.BITER = GameObject(False, True, True, 0, 21, sframes=8, sfps=20)
# row 22
GameObject.BLADDER = GameObject(False, True, True, 0, 22, sframes=8, sfps=20)
# row 23
GameObject.MAGICWALL = GameObject(False, False, True, 0, 23, sframes=8, sfps=20)
# row 24
GameObject.AMOEBA = GameObject(False, False, True, 0, 24, sframes=8, sfps=20)
# row 25
GameObject.SLIME = GameObject(False, False, True, 0, 25, sframes=8, sfps=20)
# row 26 - 30
GameObject.ROCKFORDBLINK = GameObject(False, True, True, 0, 26, sframes=8, sfps=20)
GameObject.ROCKFORDTAP = GameObject(False, True, True, 0, 27, sframes=8, sfps=20)
GameObject.ROCKFORDTAPBLINK = GameObject(False, True, True, 0, 28, sframes=8, sfps=20)
GameObject.ROCKFORDLEFT = GameObject(False, True, True, 0, 29, sframes=8, sfps=20)
GameObject.ROCKFORDRIGHT = GameObject(False, True, True, 0, 30, sframes=8, sfps=20)
# row 31
GameObject.DIAMOND = GameObject(True, False, True, 0, 31, sframes=8, sfps=20)
# row 32
GameObject.ROCKFORDSTIRRING = GameObject(False, True, True, 0, 32, sframes=8, sfps=20)
# row 33   @todo hammer
# row 34
GameObject.MEGABOULDER = GameObject(True, False, True, 0, 34)
GameObject.SKELETON = GameObject(True, False, True, 1, 34)
GameObject.GRAVITYSWITCH = GameObject(False, False, False, 2, 34)
GameObject.GRAVITYSWITCHON = GameObject(False, False, False, 3, 34)
GameObject.WALLSLOPEDUPRIGHT = GameObject(True, False, True, 4, 34)
GameObject.WALLSLOPEDUPLEFT = GameObject(True, False, True, 5, 34)
GameObject.WALLSLOPEDDOWNLEFT = GameObject(True, False, True, 6, 34)
GameObject.WALLSLOPEDDOWNRIGHT = GameObject(True, False, True, 7, 34)
# row 35
GameObject.DIRTSLOPEDUPRIGHT = GameObject(True, False, True, 0, 35)
GameObject.DIRTSLOPEDUPLEFT = GameObject(True, False, True, 1, 35)
GameObject.DIRTSLOPEDDOWNLEFT = GameObject(True, False, True, 2, 35)
GameObject.DIRTSLOPEDDOWNRIGHT = GameObject(True, False, True, 3, 35)
GameObject.STEELWALLSLOPEDUPRIGHT = GameObject(True, False, True, 4, 35)
GameObject.STEELWALLSLOPEDUPLEFT = GameObject(True, False, True, 5, 35)
GameObject.STEELWALLSLOPEDDOWNLEFT = GameObject(True, False, True, 6, 35)
GameObject.STEELWALLSLOPEDDOWNRIGHT = GameObject(True, False, True, 7, 35)
# row 36
GameObject.NITROFLASK = GameObject(True, False, True, 0, 36)
GameObject.DIRTBALL = GameObject(True, False, True, 1, 36)
GameObject.REPLICATORSWITCHON = GameObject(False, False, False, 2, 36)
GameObject.REPLICATORSWITCHOFF = GameObject(False, False, False, 3, 36)
GameObject.AMOEBAEXPLODE = GameObject(False, False, False, 4, 36, sframes=4, sfps=10)
# row 37
GameObject.AMOEBARECTANGLE = GameObject(False, True, True, 0, 37, sframes=8, sfps=10)
# row 38
GameObject.REPLICATOR = GameObject(False, False, False, 0, 38, sframes=8, sfps=20)
# row 39
GameObject.LAVA = GameObject(False, False, True, 0, 39, sframes=8, sfps=20)
# row 40
GameObject.CONVEYORRIGHT = GameObject(False, False, True, 0, 40, sframes=8, sfps=20)
# row 41
GameObject.CONVEYORLEFT = GameObject(False, False, True, 0, 41, sframes=8, sfps=20)
# row 42
GameObject.DRAGONFLY = GameObject(False, True, True, 0, 42, sframes=8, sfps=20)
# row 43
GameObject.FLYINGDIAMOND = GameObject(True, False, True, 0, 43, sframes=8, sfps=20)
# row 44
GameObject.DIRTLOOSE = GameObject(False, False, True, 0, 44)
GameObject.CONVEYORDIRECTIONSWITCHNORMAL = GameObject(False, False, False, 1, 44)
GameObject.CONVEYORDIRECTIONSWITCHCHANGED = GameObject(False, False, False, 2, 44)
GameObject.CONVEYORDIRECTIONSWITCHOFF = GameObject(False, False, False, 3, 44)
GameObject.CONVEYORDIRECTIONSWITCHON = GameObject(False, False, False, 4, 44)
GameObject.FLYINGBOULDER = GameObject(False, True, True, 5, 44)
GameObject.COCONUT = GameObject(False, False, True, 6, 44)
# row 45
GameObject.NUTCRACK = GameObject(False, False, False, 0, 45, sframes=4, sfps=10)
GameObject.ROCKETRIGHT = GameObject(False, False, True, 4, 45)
GameObject.ROCKETUP = GameObject(False, False, True, 5, 45)
GameObject.ROCKETLEFT = GameObject(False, False, True, 6, 45)
GameObject.ROCKETDOWN = GameObject(False, False, True, 7, 45)
# row 46
GameObject.ROCKETLAUNCHER = GameObject(False, False, True, 0, 46)
GameObject.ROCKFORDROCKETLAUNCHER = GameObject(False, True, True, 1, 46)
# row 49 - 50
GameObject.ROCKFORDPUSHLEFT = GameObject(False, True, True, 0, 49, sframes=8, sfps=20)
GameObject.ROCKFORDPUSHRIGHT = GameObject(False, True, True, 0, 50, sframes=8, sfps=20)


class GameState:
    class Cell:
        __slots__ = "obj", "x", "y"

        def __init__(self, obj, x, y):
            self.obj = obj  # what object is in the cell
            self.x = x
            self.y = y

    def __init__(self, tilesheet, graphics_fps, tile_image_numcolumns):
        self.tile_image_numcolumns = tile_image_numcolumns
        self.graphics_fps = graphics_fps
        self.update_timestep = 1 / 10   # game logic updates every 0.1 seconds
        self.level = 1
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
        for y in range(self.height):
            for x in range(self.width):
                self.cave.append(self.Cell(GameObject.EMPTY, x, y))
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
            0x00: GameObject.EMPTY,
            0x01: GameObject.DIRT,
            0x02: GameObject.BRICK,
            0x03: GameObject.MAGICWALL,
            0x04: GameObject.OUTBOXCLOSED,
            0x05: GameObject.OUTBOXBLINKING,
            0x07: GameObject.STEEL,
            0x08: GameObject.FIREFLY,
            0x09: GameObject.FIREFLY,
            0x0a: GameObject.FIREFLY,
            0x0b: GameObject.FIREFLY,
            0x10: GameObject.BOULDER,
            0x12: GameObject.BOULDER,
            0x14: GameObject.DIAMOND,
            0x16: GameObject.DIAMOND,
            0x25: GameObject.ROCKFORDBIRTH,
            0x30: GameObject.BUTTERFLY,
            0x31: GameObject.BUTTERFLY,
            0x32: GameObject.BUTTERFLY,
            0x33: GameObject.BUTTERFLY,
            0x38: GameObject.ROCKFORD,
            0x3a: GameObject.AMOEBA
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
            for y in range(y1 + 1, y1 + height - 1):
                self.draw_line(fillobject, x1 + 1, y, width - 2, 'r')

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
        self.cave[x + y * self.width].obj = obj
        self.tiles[x, y] = obj.spritex + self.tile_image_numcolumns * obj.spritey
        # animation is handled by the graphics refresh

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
        return self.cave[x + y * self.width + dirxy[direction]].obj

    def next_level(self):
        self.level = (self.level % len(caves.CAVES)) + 1
        self.load_c64level()

    def tiles_with_animations(self):
        return [cell for cell in self.cave if cell.obj.sframes]

    def update(self):
        self.timeremaining = self.timelimit - datetime.datetime.now()
        if self.timeremaining.seconds <= 0:
            self.timeremaining = datetime.timedelta(0)
        # sweep
        # @todo

        # place something randomly:
        # obj = random.choice([GameObject.ROCKFORDBLINK,
        #                      GameObject.ROCKFORDTAP,
        #                      GameObject.ROCKFORDTAPBLINK,
        #                      GameObject.ROCKFORDLEFT,
        #                      GameObject.ROCKFORDRIGHT,
        #                      GameObject.ROCKFORDPUSHLEFT,
        #                      GameObject.ROCKFORDPUSHRIGHT,
        #                      GameObject.EXPLOSION,
        #                      GameObject.FIREFLY,
        #                      GameObject.BUTTERFLY,
        #                      GameObject.STONEFLY,
        #                      GameObject.AMOEBA,
        #                      GameObject.ALTBUTTERFLY,
        #                      GameObject.ALTFIREFLY,
        #                      GameObject.COW,
        #                      GameObject.GHOST,
        #                      GameObject.BITER,
        #                      GameObject.BLADDER,
        #                      GameObject.AMOEBARECTANGLE,
        #                      GameObject.DRAGONFLY,
        #                      GameObject.MAGICWALL,
        #                      GameObject.DIAMOND,
        #                      GameObject.FLYINGDIAMOND,
        #                      GameObject.WATER,
        #                      GameObject.REPLICATOR,
        #                      GameObject.BOMB,
        #                      GameObject.BOMBEXPLODE,
        #                      GameObject.BONUSBG,
        #                      GameObject.COVERED,
        #                      GameObject.REPLICATOR,
        #                      GameObject.LAVA,
        #                      GameObject.IGNITEDBOMB])
        # self.draw_single(obj, random.randrange(1, self.tiles.width - 1), random.randrange(1, self.tiles.height - 1))


def start():
    window = BoulderWindow("Bouldertiles")
    window.start()
    window.mainloop()


if __name__ == "__main__":
    start()

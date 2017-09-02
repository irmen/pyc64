"""
Gem Snag - a Boulderdash clone.

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
import time
from PIL import Image
from .game import GameState, GameObject

# @todo fix magic wall : should not spin at the start


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

    def get_tiles(self, x, y, width, height):
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            raise ValueError("tile xy out of bounds")
        if width <=0 or x + width > self.width or height <= 0 or y + height >= self.height:
            raise ValueError("width or heigth out of bounds")
        start = x + self.width * y
        result = []
        for dy in range(height):
            result.append(self.tiles[start + self.width * dy: start + self.width * dy + width])
        return result

    def all_dirty(self):
        for i in range(self.width * self.height):
            self.dirty_tiles[i] = True

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

    def __init__(self, title, fps=30, scale=2, c64colors=False):
        super().__init__()
        self.update_fps = fps
        self.update_timestep = 1 / fps
        self.scalexy = scale
        if self.playfield_columns <= 0 or self.playfield_columns > 128 or self.playfield_rows <= 0 or self.playfield_rows > 128:
            raise ValueError("invalid playfield size")
        if self.visible_columns <= 0 or self.visible_columns > 128 or self.visible_rows <= 0 or self.visible_rows > 128:
            raise ValueError("invalid visible size")
        if self.scalexy not in (1, 2, 3, 4):
            raise ValueError("invalid scalexy factor")
        self.geometry("+200+40")
        self.configure(borderwidth=16, background="black")
        self.wm_title(title)
        self.appicon = tkinter.PhotoImage(data=pkgutil.get_data(__name__, "gfx/gdash_icon_48.gif"))
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
        self.uncover_tiles = set()
        self.tile_image_numcolumns = 0
        self.view_x = 0
        self.view_y = 0
        self.canvas.view_x = self.view_x
        self.canvas.view_y = self.view_y
        self.create_tile_images(c64colortiles=c64colors)
        self.font_tiles_startindex = self.create_font_tiles()
        self.bind("<KeyPress>", self.keypress)
        self.bind("<KeyRelease>", self.keyrelease)
        self.scorecanvas.pack(pady=(0, 10))
        self.canvas.pack()
        self.gfxupdate_starttime = None
        self.game_update_dt = None
        self.graphics_update_dt = None
        self.graphics_frame = 0
        self.popup_frame = 0
        self.gamestate = GameState(self)

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
            if self.gamestate.idle["uncover"]:
                self.uncover_tiles = set(range(self.playfield_rows * self.playfield_columns))
                self.gamestate.idle["uncover"] = False
            self.repaint()
        self.gfxupdate_starttime = now
        self.after(1000 // 120, self.tick_loop)

    def keypress(self, event):
        if event.keysym.startswith("Shift") or event.state & 1:
            self.gamestate.movement.start_grab()
        if event.keysym == "Down":
            self.gamestate.movement.start_down()
        elif event.keysym == "Up":
            self.gamestate.movement.start_up()
        elif event.keysym == "Left":
            self.gamestate.movement.start_left()
        elif event.keysym == "Right":
            self.gamestate.movement.start_right()
        elif event.keysym == "Escape":
            if not self.uncover_tiles:
                self.popup_frame = 0
                if self.gamestate.rockford_cell:
                    self.gamestate.explode(self.gamestate.rockford_cell)
                if self.gamestate.lives > 0:
                    self.gamestate.life_lost()
                else:
                    self.gamestate.restart()
        elif event.keysym == "F1":
            self.popup_frame = 0
            if not self.uncover_tiles and self.gamestate.lives < 0:
                self.gamestate.restart()

    def keyrelease(self, event):
        if event.keysym.startswith("Shift") or not (event.state & 1):
            self.gamestate.movement.stop_grab()
        if event.keysym == "Down":
            self.gamestate.movement.stop_down()
        elif event.keysym == "Up":
            self.gamestate.movement.stop_up()
        elif event.keysym == "Left":
            self.gamestate.movement.stop_left()
        elif event.keysym == "Right":
            self.gamestate.movement.stop_right()
        if event.keysym == "Return":
            self.gamestate.cycle_level()

    def repaint(self):
        self.graphics_frame += 1
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

        if self.popup_frame > self.graphics_frame:
            for index, tile in self.tilesheet.dirty():
                self.canvas.itemconfigure(self.c_tiles[index], image=self.tile_images[tile])
            return
        elif self.popup_tiles_save:
            self.popup_close()

        if self.uncover_tiles:
            # perform random uncover animation before the level starts
            for _ in range(int(30 * 30 / self.update_fps)):
                reveal = random.randrange(1 + self.playfield_columns, self.playfield_columns * (self.playfield_rows - 1))
                revealy, revealx = divmod(reveal, self.playfield_columns)
                self.uncover_tiles.discard(reveal)
                tile = self.tilesheet[revealx, revealy]
                self.canvas.itemconfigure(self.c_tiles[reveal], image=self.tile_images[tile])
            covered = GameObject.COVERED
            animframe = int(covered.sfps / self.update_fps * self.graphics_frame) % covered.sframes
            tile = self.sprite2tile(covered, animframe)
            for index in self.uncover_tiles:
                self.canvas.itemconfigure(self.c_tiles[index], image=self.tile_images[tile])
            if len(self.uncover_tiles) < self.playfield_columns * self.playfield_rows // 4:
                self.uncover_tiles = set()   # this ends the uncover animation and starts the level
                self.tilesheet.all_dirty()
        else:
            if self.gamestate.rockford_cell:
                # moving left/right
                if self.gamestate.movement.direction == "l" \
                        or (self.gamestate.movement.direction in ("u", "d") and self.gamestate.movement.lastXdir == "l"):
                    spritex, spritey, sframes, sfps = GameObject.ROCKFORD.left
                elif self.gamestate.movement.direction == "r" \
                        or (self.gamestate.movement.direction in ("u", "d") and self.gamestate.movement.lastXdir == "r"):
                    spritex, spritey, sframes, sfps = GameObject.ROCKFORD.right
                # handle rockford idle state/animation
                elif self.gamestate.idle["tap"] and self.gamestate.idle["blink"]:
                    spritex, spritey, sframes, sfps = GameObject.ROCKFORD.tapblink
                elif self.gamestate.idle["tap"]:
                    spritex, spritey, sframes, sfps = GameObject.ROCKFORD.tap
                elif self.gamestate.idle["blink"]:
                    spritex, spritey, sframes, sfps = GameObject.ROCKFORD.blink
                else:
                    spritex, spritey, sframes, sfps = GameObject.ROCKFORD.spritex, GameObject.ROCKFORD.spritey,\
                                                      GameObject.ROCKFORD.sframes, GameObject.ROCKFORD.sfps
                if sframes:
                    animframe = int(sfps / self.update_fps *
                                    (self.graphics_frame - self.gamestate.rockford_cell.anim_start_gfx_frame)) % sframes
                else:
                    animframe = 0
                self.tilesheet[self.gamestate.rockford_cell.x, self.gamestate.rockford_cell.y] = \
                    self.sprite2tile((spritex, spritey), animframe)
            # other animations:
            for cell in self.gamestate.cells_with_animations():
                obj = cell.obj
                animframe = int(obj.sfps / self.update_fps * (self.graphics_frame - cell.anim_start_gfx_frame))
                tile = self.sprite2tile(obj, animframe)
                self.tilesheet[cell.x, cell.y] = tile
                if animframe >= obj.sframes and obj.anim_end_callback:
                    # the animation reached the last frame
                    obj.anim_end_callback(cell)
            # flash
            if self.gamestate.flash > self.gamestate.frame:
                self.configure(background="yellow" if self.graphics_frame % 2 else "black")
            elif self.gamestate.flash > 0:
                self.configure(background="black")
            for index, tile in self.tilesheet.dirty():
                self.canvas.itemconfigure(self.c_tiles[index], image=self.tile_images[tile])

    def sprite2tile(self, gameobject_or_spritexy, animframe=0):
        if isinstance(gameobject_or_spritexy, GameObject):
            if gameobject_or_spritexy.sframes:
                return gameobject_or_spritexy.spritex + self.tile_image_numcolumns * gameobject_or_spritexy.spritey +\
                       animframe % gameobject_or_spritexy.sframes
            return gameobject_or_spritexy.spritex + self.tile_image_numcolumns * gameobject_or_spritexy.spritey
        return gameobject_or_spritexy[0] + self.tile_image_numcolumns * gameobject_or_spritexy[1] + animframe

    def create_tile_images(self, c64colortiles=False):
        tile_filename = "c64_gfx.png" if c64colortiles else "boulder_rush.png"
        with Image.open(io.BytesIO(pkgutil.get_data(__name__, "gfx/"+tile_filename))) as tile_image:
            if c64colortiles:
                tile_image = tile_image.copy().convert('P', 0)
                palette = tile_image.getpalette()
                assert 768 - palette.count(0) < 16
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
        font_tiles_startindex = len(self.tile_images)
        with Image.open(io.BytesIO(pkgutil.get_data(__name__, "gfx/font.png"))) as image:
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
        return font_tiles_startindex

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
        if not self.uncover_tiles and self.popup_frame < self.graphics_frame:
            self.gamestate.update(self.graphics_frame)
        self.gamestate.update_scorebar()

    def text2tiles(self, text):
        return [self.font_tiles_startindex + ord(c) for c in text]

    def popup(self, text):
        lines = []
        width = int(self.visible_columns * 0.6)
        for line in text.splitlines():
            output = ""
            for word in line.split():
                if len(output) + len(word) < (width + 1):
                    output += word + " "
                else:
                    lines.append(output.rstrip())
                    output = word + " "
            if output:
                lines.append(output.rstrip())
            else:
                lines.append(None)
        bchar = "\x0e"
        x, y = (self.visible_columns - width - 6) // 2, self.visible_rows // 4
        popupwidth = width + 6
        popupheight = len(lines) + 6
        self.popup_tiles_save = (
            x, y, popupwidth, popupheight,
            self.tilesheet.get_tiles(x, y, popupwidth, popupheight)
        )
        self.tilesheet.set_tiles(x, y, [self.sprite2tile(GameObject.STEELSLOPEDUPLEFT)] +
                                 [self.sprite2tile(GameObject.STEEL)] * (width + 4) +
                                 [self.sprite2tile(GameObject.STEELSLOPEDUPRIGHT)])
        self.tilesheet.set_tiles(x + 1, y + 1, self.text2tiles(bchar * (width + 4)))
        self.tilesheet[x, y + 1] = self.sprite2tile(GameObject.STEEL)
        self.tilesheet[x + width + 5, y + 1] = self.sprite2tile(GameObject.STEEL)
        y += 2
        lines.insert(0, "")
        lines.append("")
        for line in lines:
            if not line:
                line = " "
            tiles = self.text2tiles(bchar + " " + line.ljust(width) + " " + bchar)
            self.tilesheet[x, y] = self.sprite2tile(GameObject.STEEL)
            self.tilesheet[x + width + 5, y] = self.sprite2tile(GameObject.STEEL)
            self.tilesheet.set_tiles(x + 1, y, tiles)
            y += 1
        self.tilesheet[x, y] = self.sprite2tile(GameObject.STEEL)
        self.tilesheet[x + width + 5, y] = self.sprite2tile(GameObject.STEEL)
        self.tilesheet.set_tiles(x + 1, y, self.text2tiles(bchar * (width + 4)))
        self.tilesheet.set_tiles(x, y + 1, [self.sprite2tile(GameObject.STEELSLOPEDDOWNLEFT)] +
                                 [self.sprite2tile(GameObject.STEEL)] * (width + 4) +
                                 [self.sprite2tile(GameObject.STEELSLOPEDDOWNRIGHT)])
        self.popup_frame = self.graphics_frame + self.update_fps * 5   # popup remains for 5 seconds

    def popup_close(self):
        x, y, width, height, saved_tiles = self.popup_tiles_save
        for tiles in saved_tiles:
            self.tilesheet.set_tiles(x, y, tiles)
            y += 1
        self.popup_tiles_save = None


def start(args):
    import argparse
    ap = argparse.ArgumentParser(description="Gem Snag - a Boulderdash clone")
    ap.add_argument("-f", "--fps", type=int, help="frames per second", default=30)
    ap.add_argument("-s", "--scale", type=int, help="graphics scale factor", default=2, choices=(1, 2, 3, 4))
    ap.add_argument("-c", "--c64colors", help="use Commodore-64 colors", action="store_true")
    args = ap.parse_args(args)
    window = BoulderWindow("Gem Snag", args.fps, args.scale, args.c64colors)
    window.start()
    window.mainloop()


if __name__ == "__main__":
    start(sys.argv[1:])

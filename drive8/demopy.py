from math import sin, cos, radians
from drive8 import fib

screen.clear()
screen.shifted = False
screen.screen = 0
screen.border = 5
screen.text = 4
print("\n   hi from c-64 python!" + "\n" * 7)

print("first 30 fibonacci numbers:")
fibs = fib.fibonacci()
for i in range(30):
    f = next(fibs)
    print(f, end=", ")
print("")


mem[251] = 1000//60  # set 60hz refresh

# eyes
x1 = screen.columns//2 - 7
x2 = screen.columns//2 + 6
facey = screen.rows//2
colors[x1 + (facey-9) * screen.columns:x1 + (facey-4) * screen.columns:screen.columns] = 15
chars[x1 + (facey-9) * screen.columns:x1 + (facey-4) * screen.columns:screen.columns] = 81
colors[x2 + (facey-9) * screen.columns:x2 + (facey-4) * screen.columns:screen.columns] = 15
chars[x2 + (facey-9) * screen.columns:x2 + (facey-4) * screen.columns:screen.columns] = 81

# mouth
for i in range(91, 269, 4):
    ri = radians(i)
    x, y = sin(ri) * 14 + screen.columns/2, facey - cos(ri) * 10
    colors[x, y] = 1
    chars[x, y] = 81   # circle
    sync()

# define spritedata
mem[12288: 12288+63] = [
    0, 3, 240, 0, 255, 248, 0, 7, 252,
    0, 15, 252, 0, 4, 136, 0, 15, 252, 0, 4, 136,
    0, 15, 252, 128, 26, 170, 255, 250, 170,
    128, 58, 170, 1, 255, 254, 0, 21, 84,
    0, 10, 170, 0, 21, 84, 0, 42, 170,
    0, 21, 84, 0, 42, 170, 0, 85, 84,
    0, 42, 170, 0, 85, 84]

if not screen.sprites:
    raise InterruptedError("no sprites")

# setup sprites
for s in range(screen.sprites):
    sprite(s, x=0, y=0, dx=s&2, dy=s&4, color=s+8, pointer=12288, enabled=True)

# animate sprites
r = 0.0
while True:
    for s in range(screen.sprites):
        sx = int(170 + cos(r * 1.345 - s * 0.25) * 120)
        sy = int(140 + sin(r - s * 0.2) * 80)
        sprite(s, x=sx, y=sy)
    sync()   # sync to refresh hz
    r += 0.05

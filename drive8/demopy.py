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
colors[13 + 3 * 40:13 + 8 * 40:40] = 15
chars[13 + 3 * 40:13 + 8 * 40:40] = 81
colors[26 + 3 * 40:26 + 8 * 40:40] = 15
chars[26 + 3 * 40:26 + 8 * 40:40] = 81

# mouth
for i in range(91, 269, 4):
    ri = radians(i)
    x, y = sin(ri) * 14 + 20, 13 - cos(ri) * 10
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

# set sprite colors and pointers
for s in range(8):
    mem[53287 + s] = s + 8
    mem[2040 + s] = 12288//64

# set sprite flags
mem[53277] = 204
mem[53271] = 240
mem[53269] = 255

# animate sprites
r = 0.0
while True:
    mem[53264] = 0
    for s in range(8):
        sx = int(170 + cos(r * 1.345 - s * 0.25) * 120)
        sy = int(140 + sin(r - s * 0.2) * 80)
        mem[53248 + s*2] = sx & 255
        mem[53249 + s*2] = sy & 255
        if sx > 255:
            mem[53264] |= 1 << s    # x msb
    sync()   # sync to refresh hz
    r += 0.05

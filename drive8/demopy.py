from math import sin, cos, radians
from drive8 import fib

cls()
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

for i in range(91, 269, 4):
    ri = radians(i)
    x, y = sin(ri) * 14 + 20, 13 - cos(ri) * 10
    chars[x, y] = 81   # circle
    colors[x, y] = 1

chars[13 + 3 * 40:13 + 8 * 40:40] = 81
colors[13 + 3 * 40:13 + 8 * 40:40] = 15
chars[26 + 3 * 40:26 + 8 * 40:40] = 81
colors[26 + 3 * 40:26 + 8 * 40:40] = 15

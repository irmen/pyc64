from math import sin, cos, radians

cls()
screen.shifted = False
screen.screen = 0
screen.border = 5
screen.text = 4
print("\n   hi from c-64 python!\n\n\n\n\n\n\n")


def fibonacci():
    a, b = 0, 1
    while True:
        yield a
        a, b = b, a + b

print("first 20 fibonacci numbers:")
fibs = fibonacci()
for x in range(20):
    print(next(fibs), end=", ")
print()
q = 999

for i in range(91, 269, 4):
    ri = radians(i)
    x, y = sin(ri) * 14 + 20, 13 - cos(ri) * 10
    chars[x, y] = 81   # circle
    colors[x, y] = 1

chars[13 + 3 * 40: 13 + 8 * 40: 40] = 81
colors[13 + 3 * 40: 13 + 8 * 40: 40] = 15
chars[26 + 3 * 40: 26 + 8 * 40: 40] = 81
colors[26 + 3 * 40: 26 + 8 * 40: 40] = 15

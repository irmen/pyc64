10 color 6,0,7:cls:poke 53272,21
11 rem determine screen size
12 sys 65517: cols=peek(781): rows=peek(782)
20 for x=0 to cols-1
21 poke 1024+x,67: poke 1024+cols*(rows-1)+x,67
22 next x
30 for y=1 to rows-2
31 poke 1024+y*cols, 93: poke 1023+cols+y*cols, 93
32 next y
40 poke 1024,85:poke 1023+cols,73:poke1024+cols*(rows-1),74:poke1023+cols*rows,75
100 scroll "l", 1, 1, cols-2, rows-2
105 y=rndi(1,rows-1): poke 1022+cols+y*cols,[42,81,46,43][rndi(0,4)]
110 c=rndi(1,16):poke 55294+cols+y*cols,c
120 cursor cols//2-14, rows//2: print(" oh my, it's full of stars!");
200 sync
210 goto 100

10 color 0,0,7:cls:poke 53272,21
11 rem determine screen size
12 sys 65517: cols=peek(781): rows=peek(782)
100 scroll "l":y=rndi(0,rows): poke 1023+cols+y*cols,[42,81,46,43][rndi(0,4)]
110 c=rndi(1,16):poke 55295+cols+y*cols,c
120 cursor cols//2-14, rows//2: print(" oh my, it's full of stars!");
200 sync
210 goto 100

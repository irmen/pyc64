10 rem ---first setup the screen---
11 rem determine screen size
12 sys 65517: cols=peek(781): rows=peek(782)
20 cls: poke 53272,23
30 poke 53280,2: poke 53281,0: poke 646,7
40 cursor cols/2-4,rows/2-2:print"hello"
50 cursor cols/2-4,rows/2:print"there!"
70 sleep 0.2
99 rem ---draw color bars---
100 for color=0 to 15
110 for y=0 to rows-1
120 poke 1024+color+y*cols, 160: poke 1024+y*cols+cols-1-color, 160
130 poke 55296+color+y*cols, color: poke 55296+y*cols+cols-1-color, color
140 next y
150 if color > 8 then goto 200
160 for x=color to cols-1-color
170 poke 1024+x+color*cols, 105 : poke 55296+x+color*cols, color
180 poke 1024+x+(rows-1-color)*cols, 105 : poke 55296+x+(rows-1-color)*cols, color
190 next x
200 next color
299 rem ---charset flipping and border flash---
300 for i=0 to 15
310 poke 53272, 21: if i&1 then goto 320
311 poke 53272, 23
320 poke 53280, i
330 sleep 0.3
340 next i
400 print"press u,d,l,r to scroll!"
410 get k: if k=="" goto 410
420 scroll k
430 goto 410

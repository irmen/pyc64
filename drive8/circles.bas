10 poke53280,0:poke53281,0
11 rem determine screen size
12 sys 65517: cols=peek(781): rows=peek(782)
20 for rs=1.25to 0.0499step -0.2
30 cls
40 for r=2 to (cols-1)/2 step 2
50 for i=0 to 2*π step rs
60 x=r*sin(i)+cols/2
70 y=r*cos(i)+rows/2
80 q=int(i/π*8)
90 chars=(45,78,78,93,93,77,77,45,45,78,78,93,93,77,77,45)
100 c=chars[q]:f=r/2
110 if y<0 or y>rows-1 goto 200
120 poke 1024+(x+0.5)+cols*int(y+0.5), c
130 poke55296+(x+0.5)+cols*int(y+0.5), f
200 next i
210 next r
220 sleep 0.2
230 next rs

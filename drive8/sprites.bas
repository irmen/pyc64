10 for s=0 to 7
20 poke 53287+s, s+8: poke 2040+s, 192
30 next s
40 poke 53277,204 : poke 53271, 240: poke 53269, 255
45 poke 53280,11: poke 53281,0: poke 646,6
50 cls: list
60 print: print"   dalek sprite demo!!!";
70 for i=0 to 62
80 read x: poke 12288+i,x
90 next i
100 r=0
110 for s=0 to 7
115 sx=170+cos(r*1.345-s*0.25)*120: sy = 140+sin(r-s*0.2)*80
120 poke 53248+s*2,int(sx)&255: poke 53249+s*2,int(sy)&255
130 if sx > 255 goto 150
140 poke 53264, peek(53264) & ~(1<<s): goto 160
150 poke 53264, peek(53264) | 1<<s
160 next s
180 r=r+0.05: goto 110
1040 data 0,3,240,0,255,248,0,7,252
1050 data 0,15,252
1060 data 0,4,136,0,15,252,0,4,136
1070 data 0,15,252,128,26,170,255,250,170
1080 data 128,58,170,1,255,254,0,21,84
1090 data 0,10,170,0,21,84,0,42,170
1100 data 0,21,84,0,42,170,0,85,84
1110 data 0,42,170,0,85,84

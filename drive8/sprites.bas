10 for s=0 to 7
20 poke 53287+s, s+8:
30 next s
40 poke 53277,204 : poke 53271, 240: poke 53269, 255
45 poke 53280,11: poke 53281,0: poke 646,6
50 cls: list
60 print: print"   sprite demo!!!";
100 r=0
110 for s=0 to 7
115 sx=170+cos(r*1.345-s*0.25)*120: sy = 140+sin(r-s*0.2)*80
120 poke 53248+s*2,int(sx)&255: poke 53249+s*2,int(sy)&255
130 if sx > 255 goto 150
140 poke 53264, peek(53264) & ~(1<<s): goto 160
150 poke 53264, peek(53264) | 1<<s
160 next s
180 r=r+0.05: goto 110

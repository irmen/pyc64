10 poke646,1: cls
20 print "joystick nr 2 via numpad"
30 s = 1024 + 5 + 40*5
40 j = peek(56320)
50 fire=81:up=81:down=81:left=81:right=81
60 if j & 16 then fire = 46
70 if j & 1 then up = 46
80 if j & 2 then down = 46
90 if j & 4 then left = 46
100 if j & 8 then right = 46
110 poke s-40,up:pokes+40,down:pokes-1,left:pokes+1,right
120 poke s+5,fire
130 sync
140 goto 40

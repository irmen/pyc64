10 poke646,1:?chr(147)
20 print "joystick nr 2 via numpad"
30 s = 1024 + 5 + 40*5
40 j = peek(56320)
50 fire=46:up=46:down=46:left=46:right=46
60 if not(j & 16) then fire = 81
70 if j & 1 then left = 81
80 if j & 2 then right = 81
90 if j & 4 then up = 81
100 if j & 8 then down = 81
110 poke s-40,up:pokes+40,down:pokes-1,left:pokes+1,right
120 poke s+5,fire
130 sync
140 goto 40

5 poke 53265,19:poke 53270,192
6 poke 53248,100:poke53249,100:poke53269,1
10 for i=0 to 25
20 for j=0 to 7
30 poke 53270,j | 192:poke53265,j | 16
40 sync
50 next j
60 scroll "rd"
70 next i
80 poke 53265,27:poke 53270,200

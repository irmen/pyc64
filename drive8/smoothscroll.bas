10 for i=0 to 25
20 for j=1 to 8
25 sync:sync
30 poke 53270,j:poke53265,j
50 next j
60 scroll "rd"
70 next i
80 poke 53265, 27

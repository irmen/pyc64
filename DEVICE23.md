# What is Device23?

Device23 is a virtual device which enable pyc64 to do http web requests.
It is mapped as physical device 23 and you use it "opening" web page like:

```basic
  100 print "open test"
  200 open5,23,0,"www.c64-wiki.com"
  300 input# 5,page$
  350 print page$
  400 close 5
```





To get it working realemulator 



1. intercept calls to $FFCF KERNAL CHRIN 
and try to understand if logical device (A=5 in the example) is mapped. 

It snoops the following page zero locations:

    $B8            Current Logical File Number (5 in the example)
    $B9            Current Secondary Address (0 in the example)
    $BA            Current Device Number
    $BB-$BC        Pointer: Current Filename
    $99            Current  input device
    
When CHRIN routine is called, the next byte of data available from this
device is returned in the Accumulator.
Subsequent calls to this routine will cause the next character in the
line to be read from the screen and returned in the Accumulator, until
the carriage return character is returned to indicate the end of the
line. 



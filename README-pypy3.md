
# Speed up
pypy is a way to speed up your pyc64 emualtor
pypy is a Just in Time compiler.

Using pypy you can speed up 6502 emulation, and it is quite easy to set up.

Trace mode can slow down the emulator

*pypy3 version 3.6.9 is supported*

## Installing and running Pypy3 
Under Ubuntu add the following repository https://launchpad.net/~pypy/+archive/ubuntu/ppa

A convenient install is

  sudo add-apt-repository ppa:pypy/ppa
  sudo apt install pypy3 pypy3-tk pypy3-dev libjpeg-dev
  curl -O https://bootstrap.pypa.io/get-pip.py -o get-pip.py  
  pypy3 get-pip.py  
  pypy3 -m pip install -r requirements.txt
  # Ensure pillow correctly installed (sometimes you get errors)
  pypy3 -m pip install -U Pillow
  apt-get install libncurses-dev
  # Test with
  pypy3  startreal64.py  \$
The pip installation will be local to your user.


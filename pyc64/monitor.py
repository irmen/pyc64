# Learning monitor
# Curses based

from curses import *
from curses.textpad import Textbox, rectangle

from .memory import ScreenAndMemory
from .cputools import CPU

class MonitorWindow:
    def __init__(self, memory, stdscr=initscr()):
        self.memory=memory
        self.cpu=None
        self.stdscr = stdscr
        self.stdscr.clear()
        #noecho()
        #cbreak() 
        self.messages=[]
        disassemble_buffer_size=20
        # Set here the size of the disassemble buffer
        for x in range(1,disassemble_buffer_size):
            self.messages.append("")
        x,y=stdscr.getmaxyx()
        self.say("Screen size {} x {}".format(x,y))
        minimal_size=20+disassemble_buffer_size
        if y<minimal_size:
            self.say("WARNING:: *Screen too small* Minimal rows:{} ".format(minimal_size))
        # #self.wm_title("Monitor")
        # #self.frame.geometry("+100+40")
        # label = tk.Label(text="ZeroPage")
        # label.pack()
        # self.zp_box = tk.Text(width=(16*2*3)+15+1)
        # self.zp_box.pack()
        # #self.zp_box_refresh()
        # self.zp_box_refresh()
        # #self.frame.pack()
    
    def set_cpu(self,cpu):
        self.cpu=cpu

    def refresh(self):
        self.stdscr.clear()
        self.stdscr.addstr(0,0," ** Pyc64 Learning Monitor ** ")
        self.draw_zero_page()
        self.stdscr.addstr("Current Disassemble\n",A_REVERSE)
        for m in self.messages:
            try:
                self.stdscr.addstr(m+"\n")
            # GG On unbuntu we get _curses.error: addstr() returned ERR
            except  Exception as err:
                pass        
        self.stdscr.refresh()

    def breakpoint(self):
        """
        Wait for a key  press
        """
        self.stdscr.addstr(0,0," *** Breakpoint! s= step c=continue *** ", A_REVERSE)
        # self.stdscr.nodelay(False)
        c=self.stdscr.getkey()
        return c

    def say(self,msg):
        """
        Print messages in a scrollable area
        """
        self.messages.append(msg)
        self.messages.pop(0)
        self.refresh()

    def draw_zero_page(self):                
        self.stdscr.addstr(1,0,"Zero Page Dump")
        for row in range(0,0xFF, 0x20):
            line=""
            for i in range(row, row+0x20,1):
                line=line+" {:02X}".format(self.memory[i])                
            self.stdscr.addstr("\n{:02X}  {}".format(row,line))            
        cpu=self.cpu            
        if cpu!=None:
            self.stdscr.addstr("\nStack Pointer")
            for row in range(0x100,0x1FF,0x20):
                line=""
                for i in range(row, row+0x20,1):
                    if cpu.sp==(i-0x100):
                        line=line+" [{:02X}]".format(self.memory[i])
                    else:
                        line=line+" {:02X}".format(self.memory[i])
                self.stdscr.addstr("\n{:02X} {}".format(row,line))        
            self.stdscr.addstr(
                    "\n - A=${:02x} X=${:02x} Y=${:02x} P=%{:08b} SP={:02X}"
                        .format( cpu.a, cpu.x, cpu.y, cpu.p, cpu.sp) )
        self.stdscr.addstr("\n")
    def finish(self):        
        endwin()

def test(stdscr):
    # Normally ScreenAndMemory will be passed
    s=ScreenAndMemory(columns=40, rows=25, sprites=8,rom_directory="roms",run_real_roms=False)
    cpu = CPU(memory=s.memory, pc=0xFFFF)
    m=MonitorWindow(s.memory, stdscr)
    m.set_cpu(cpu)
    m.refresh()
    m.say("Ready")    
    import time    
    for  i in range(2,18):
        m.say(" Line "+str(i))    
        if m.breakpoint()=='s':
            continue
        else:
            break
    m.refresh()
    time.sleep(1)
    m.finish()

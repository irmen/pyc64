"""
Commodore-64 simulator in 100% pure Python 3.x :)

This module is the GUI window logic, handling keyboard input
and screen drawing via tkinter bitmaps.

Written by Irmen de Jong (irmen@razorvine.net)
License: MIT open-source.
"""

import time
from pyc64.emulator import C64EmulatorWindow
from .memory import ScreenAndMemory
from .cputools import CPU
import struct

class RealC64EmulatorWindow(C64EmulatorWindow):
    welcome_message = "Running the Real ROMS!"
    update_rate = 1000/20

    def __init__(self, screen, title, roms_directory):
        super().__init__(screen, title, roms_directory, True)
        self.keypresses = []

    def keyrelease(self, event):
        pass

    def keypress(self, event):
        self.keypresses.append(event)

    def run_rom_code(self, reset):
        cpu = CPU(memory=self.screen.memory, pc=reset)
        self.real_cpu_running = cpu
        previous_cycles = 0
        mem = self.screen.memory
        old_raster = 0
        while True:
            irq_start_time = time.perf_counter()
            while time.perf_counter() - irq_start_time < 1.0/60.0:
                for _ in range(1000):
                    cpu.step()
                    if cpu.pc == 0xFFD8:
                        self.breakpointKernelSave(cpu,mem)
                    elif cpu.pc == 0xffd5:
                        self.breakpointKernelLoad(cpu,mem)
                    # set the raster line based off the number of CPU cycles processed
                    raster = (cpu.processorCycles//63) % 312
                    if raster != old_raster:
                        mem[53266] = raster and 255
                        high = mem[53265] & 0b01111111
                        if raster > 255:
                            high |= 0b10000000
                        mem[53265] = high
                        old_raster = raster
                time.sleep(0.001)
            self.irq(cpu)
            duration = time.perf_counter() - irq_start_time
            speed = (cpu.processorCycles-previous_cycles) / duration / 1e6
            previous_cycles = cpu.processorCycles            
            print("CPU simulator: PC=${:04x} A=${:02x} X=${:02x} Y=${:02x} P=%{:08b} -  clockspeed = {:.1f} MHz   "
              .format(cpu.pc, cpu.a, cpu.x, cpu.y, cpu.p, speed), end="\r")


    def breakpointKernelSave(self,cpu,ram):
        """ Ref https://github.com/irmen/ksim65/blob/d1d433c3a640e1429f8fe2755afa96ca39c4dfbb/src/main/kotlin/razorvine/c64emu/c64Main.kt#L82
        """        
        print("Kernal Save Intercept....")        
        fnlen = ram[0xb7]   # file name length
        fa = ram[0xba]      # device number
        sa = ram[0xb9]      # secondary address
        fnaddr = cpu.WordAt(0xbb)  # memory[0xbb]+256*memory[0xbc]  # file name address
        if fnlen >0:
            print("Saving...")
            fname=self.get_filename(fnaddr,fnlen,cpu)            
            startAddr= ram[cpu.a]+256*ram[cpu.a+1]
            endAddr=cpu.x+256*cpu.y                        
            print("Filename {} Start Addr:{:02X} End: {:02X} Size:{}".format(fname,startAddr,endAddr, endAddr-startAddr))
            # Write fromAddr high and low
            with open("drive8/" + fname, "wb") as file:
                file.write(startAddr.to_bytes(2, byteorder='little'))
                print("Header ok")
                for i in range(startAddr,endAddr):
                    data= ram[i].to_bytes(1, byteorder='little')
                    file.write( data )
                    print("{}".format(data))
                file.close()                
            # write data
            ram[0x90]=0 # OK
            print("Save completed")
            #success!
            cpu.pc=0xf5a9
        else:
            print("?missing file name")
            cpu.pc=0xf710 

    def get_filename(self,fnaddr,fnlen,cpu):
        fname=""
        for i in range(0,fnlen):
            fname=fname + chr(cpu.ByteAt(fnaddr+i)).lower()
        if not fname.endswith(".prg"):
            fname=fname+".prg"
        return fname         

    def breakpointKernelLoad(self,cpu,ram):
        """
        """
        if cpu.a ==0:
            fnlen = ram[0xb7]   # file name length
            fa = ram[0xba]      # device number (i.e 8)
            sa = ram[0xb9]      # secondary address (i.e 15 for disk commands)
            destinationAddress=ram[0x2b]+256*ram[0x2c]
            fnaddr = cpu.WordAt(0xbb) 
            # changePC = 0xf704)   // 'file not found'
            fname=self.get_filename(fnaddr,fnlen,cpu)
            if fnlen >0:
                try:
                    with open("drive8/" + fname, "rb") as file:
                        startAddr = struct.unpack("<H", file.read(2))[0]                    
                        print("Start Addr: {:02X}".format(startAddr))
                        prog=file.read()
                        endAddress= startAddr + len(prog)
                        ram[startAddr: endAddress] = prog
                        print("Load Completed up to: $ {:02X}".format(endAddress))
                        ram[0x90] = 0  # status OK
                        # low-high address here
                        ram[0xae]= endAddress & 0x00ff
                        high=(endAddress & 0xff00) >>8                    
                        ram[0xaf]= high
                        file.close()                
                    # success
                    cpu.pc=0xf5a9
                except FileNotFoundError:
                    cpu.pc=0xf704 # 'file not found'
            else:
                print("?missing file name")
                cpu.pc=0xf710 
        else:
            print("device not present (VERIFY command not supported)")
            cpu.pc=0xf707
    def irq(self, cpu):
        self.simulate_keystrokes()
        if hasattr(cpu, "irq"):
            cpu.irq()
        else:
            self.cpu_irq(cpu)

    def cpu_irq(self, cpu):
        # fallback for py65 library that doesn't yet have the irq() and nmi() methods
        if cpu.p & cpu.INTERRUPT:
            return
        cpu.stPushWord(cpu.pc)
        cpu.p &= ~cpu.BREAK
        cpu.stPush(cpu.p | cpu.UNUSED)
        cpu.p |= cpu.INTERRUPT
        cpu.pc = cpu.WordAt(cpu.IRQ)
        cpu.processorCycles += 7

    control_color_chars = {
        '0': 0x92,
        '1': 0x90,
        '2': 0x05,
        '3': 0x1c,
        '4': 0x9f,
        '5': 0x9c,
        '6': 0x1e,
        '7': 0x1f,
        '8': 0x9e,
        '9': 0x12,
    }

    commodore_color_chars = {
        '0': 0x00,
        '1': 0x81,
        '2': 0x95,
        '3': 0x96,
        '4': 0x97,
        '5': 0x98,
        '6': 0x99,
        '7': 0x9a,
        '8': 0x9b,
        '9': 0x00,
    }

    def simulate_keystrokes(self):
        if not self.keypresses:
            return
        num_keys = self.screen.memory[0xc6]
        while self.keypresses and num_keys < self.screen.memory[0x289]:
            event = self.keypresses.pop()
            char = event.char
            if not char or ord(char) > 255:
                char = event.keysym
            with_shift = event.state & 1
            with_control = event.state & 4
            with_alt = event.state & 8
            if (with_control or with_alt) and event.keysym in "0123456789":
                # control+number or alt+number
                if with_control:
                    petscii = self.control_color_chars[event.keysym]
                else:
                    petscii = self.commodore_color_chars[event.keysym]
            elif char == '\b':
                petscii = 0x14    # backspace ('delete')
            elif char == '\x1b':
                petscii = 0x83 if with_shift else 0x03
            elif event.keysym == "Home":
                petscii = 0x93 if with_shift else 0x13      # clear/home
            elif event.keysym == "Up":
                petscii = 0x91
            elif event.keysym == "Down":
                petscii = 0x11
            elif event.keysym == "Left":
                petscii = 0x9d
            elif event.keysym == "Right":
                petscii = 0x1d
            elif event.keysym == "Insert":
                petscii = 0x94
            elif event.keysym == "F1":
                petscii = 0x85
            elif event.keysym == "F2":
                petscii = 0x86
            elif event.keysym == "F3":
                petscii = 0x87
            elif event.keysym == "F4":
                petscii = 0x88
            elif event.keysym == "F5":
                petscii = 0x89
            elif event.keysym == "F6":
                petscii = 0x8a
            elif event.keysym == "F7":
                petscii = 0x8b
            elif event.keysym == "F8":
                petscii = 0x8c
            elif (event.keycode == 50 and with_alt) or (event.keycode == 64 and with_shift):
                charset = self.screen.memory[0xd018] & 0b00000010
                petscii = 0x8e if charset else 0x0e
            else:
                try:
                    encoded = self.screen.encode_petscii(event.char)
                    if encoded:
                        petscii = encoded[0]
                    else:
                        return
                except UnicodeEncodeError:
                    return      # not mapped
            self.screen.memory[0x277 + num_keys] = petscii
            num_keys += 1
        self.screen.memory[0xc6] = num_keys


def start():
    rom_directory = "roms"
    screen = ScreenAndMemory(columns=C64EmulatorWindow.columns,
                             rows=C64EmulatorWindow.rows,
                             sprites=C64EmulatorWindow.sprites,
                             rom_directory=rom_directory,
                             run_real_roms=True)
    emu = RealC64EmulatorWindow(screen, "Commodore-64 emulator in pure Python! - running actual roms", rom_directory)
    emu.start()
    emu.mainloop()


if __name__ == "__main__":
    start()

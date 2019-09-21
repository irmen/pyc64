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

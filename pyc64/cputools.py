"""
6502/6510 CPU utilities, requires the py65 library
http://py65.readthedocs.io

Written by Irmen de Jong (irmen@razorvine.net)
License: MIT open-source.
"""

import time
import os
import py65.monitor
import py65.devices.mpu6502


class Monitor(py65.monitor.Monitor):
    """cpu/mem monitor that accepts external memory"""
    def __init__(self, memory, stdout=None, stdin=None):
        try:
            super().__init__(stdout=stdout, stdin=stdin, memory=memory, putc_addr=None, getc_addr=None)
            self.__workaround = False
        except TypeError:
            # workaround for older version of py65
            self.memory = memory
            super().__init__(stdout=stdout, stdin=stdin)
            self.putc_addr = None
            self.getc_addr = None

    def _install_mpu_observers(self, getc_addr, putc_addr):
        # only called as workaround in case of older py65 version
        self._mpu.memory = self.memory


class CPU(py65.devices.mpu6502.MPU):
    def run(self, pc=None, microsleep=None):
        end_address = 0xffff
        self.stPushWord(end_address - 1)   # push a sentinel return address
        if pc is not None:
            self.pc = pc
        stopcodes = {0x00}        # BRK
        instructions = 0
        while True:
            if self.memory[self.pc] == 0x4c and self.WordAt(self.pc + 1) == self.pc:
                # JMP to itself, instead of looping forever we also consider this a program end
                time.sleep(2)
                break
            self.step()
            instructions += 1
            if instructions % 4000 == 0 and microsleep:
                # print("microsleep", instructions)
                microsleep()
            if self.pc == end_address:
                # when this address is reached, we consider it the end of the program
                break
            if self.memory[self.pc] in stopcodes:
                raise InterruptedError("brk instruction")

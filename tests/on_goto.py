import unittest
from pyc64.basic import BasicInterpreter, BasicError, GotoLineException
from pyc64.memory import ScreenAndMemory

class BasicEmulatorTest(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(True,True)
    def test_on_goto0(self):
        try:
            b=BasicInterpreter(ScreenAndMemory())
            b.execute_on_goto_gosub("on 1 goto 1,2")
            self.fail("unde'd statement error expected")
        except BasicError as e:
            pass
    
    def test_on_goto1(self):
        try:
            # LOADED:{0: 'rem Tester', 20: 'on 2 goto 30,40', 30: 'print "failure"', 40: 'print "success"'}
            b=BasicInterpreter(ScreenAndMemory())
            b.execute_load("load \"ongoto1\" ")
            b.execute_run("run 20")
            #b.execute_line("run 20")
            self.fail("No error?")
        except GotoLineException as gx:
            b.implementGoto(gx)
            self.assertTrue(b.running_program)
            b.program_step()
            print("CURRENT LINE:"+str(b.next_run_line_idx))
            self.assertEqual(3,b.next_run_line_idx)
            #b.execute_run("run")
            # print("***"+str(b.))
    # TODO Implement a silly test program to test the on expr syntax

if __name__ == '__main__':
    unittest.main()

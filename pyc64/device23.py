

from pyc64.cputools import CPU
# TODO: define the device class and so forth

def post_reload(memory,cpu: CPU):
    """
    This GUI thread will work probably in concurrent way.
    Changing the memory here can be dangerous.
    It is safe only on first call    
    """
    memory[0xc000]=24
    # Add a probe for $e510 which is the kernel jump for set character
    memory.intercept_read(0xe510,set_cursor)
    return "Reloaded3"

def set_cursor(address,value):
    print("Azz")
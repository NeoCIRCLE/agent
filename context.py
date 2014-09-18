import platform

""" This is the defautl context file. It replaces the Context class
    to the platform specific one.
"""

system = platform.system()

if system == "Windows":
    from windows._win32context import Context
    from win32.win32virtio import SerialPort
elif system == "Linux":
    from linux._linuxcontext import Context
    from linux.posixvirtio import SerialPort

else:
    raise NotImplementedError("Platform %s is not supported.", system)


class BaseContext():
    pass

Context
SerialPort

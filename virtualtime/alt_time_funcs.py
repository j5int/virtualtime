"""These functions are fallbacks in case we hit the occasional import lock error in datetime functions, and for tests"""

import sys
import datetime

if sys.platform.startswith('win'):
    try:
        import win32api
    except ImportError:
        win32api = None

    def alt_get_local_datetime(tz=None):
        t = win32api.GetLocalTime()
        return datetime.datetime(t[0], t[1], t[3], t[4], t[5], t[6], t[7] * 1000, tzinfo=tz)

    def alt_get_utc_datetime():
        t = win32api.GetSystemTime()
        return datetime.datetime(t[0], t[1], t[3], t[4], t[5], t[6], t[7] * 1000)

elif sys.platform.startswith('linux'):
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        class timeval(ctypes.Structure):
            _fields_ = [("seconds", ctypes.c_long),("microseconds", ctypes.c_long)]
    except (ImportError, OSError):
        ctypes = None
        libc = None
        timeval = None

    def alt_get_local_datetime():
        t = timeval()
        if libc.gettimeofday(ctypes.byref(t), None) == 0:
            return datetime.datetime.fromtimestamp(float(t.seconds) + (t.microseconds / 1000000.), None)
        raise ValueError("Error retrieving time")

    def alt_get_utc_datetime():
        t = timeval()
        if libc.gettimeofday(ctypes.byref(t), None) == 0:
            libc.tzset()
            utc_offset = (ctypes.c_int32).in_dll(libc, 'timezone').value
            return datetime.datetime.fromtimestamp(float(t.seconds) + (t.microseconds / 1000000.) + utc_offset,
                                                   None)
        raise ValueError("Error retrieving time")
else:
    def alt_get_local_datetime():
        raise NotImplementedError()

    def alt_get_utc_datetime():
        raise NotImplementedError()


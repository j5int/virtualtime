"""These functions are fallbacks in case we hit the occasional import lock error in datetime functions, and for tests"""

import sys
import datetime
import re

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

# searching for this will eliminate escaped percent-format signs
format_re = re.compile('%.')

def adjust_strftime(dt, format_str):
    format_chars = list(format_re.finditer(format_str))
    for m in reversed(format_chars):
        text = m.group(0)
        if text == '%f':
            format_str = format_str[:m.start()] + ('%06d' % getattr(dt, 'microsecond', 0)) + format_str[m.end():]
        elif text == '%z':
            tzinfo = getattr(dt, 'tzinfo', None)
            try:
                offset_td = tzinfo.utcoffset(dt) if tzinfo else None
            except NotImplementedError:
                offset_td = None
            if offset_td is not None:
                offset = offset_td.days*24*3600 + offset_td.seconds
                offset_sign, offset = ('+' if offset >= 0 else '-'), abs(offset)
                minutes, seconds = divmod(offset, 60)
                hours, minutes = divmod(minutes, 60)
                offset_str = '%c%02d%02d' % (offset_sign, hours, minutes)
            else:
                offset_str = ''
            format_str = format_str[:m.start()] + offset_str + format_str[m.end():]
        elif text == '%Z':
            tzinfo = getattr(dt, 'tzinfo', None)
            tzname = '' if tzinfo is None else tzinfo.tzname(dt)
            format_str = format_str[:m.start()] + tzname + format_str[m.end():]
    return format_str

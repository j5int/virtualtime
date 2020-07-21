#!/usr/bin/env python

"""This checks what happens when trying to use datetime functions that rely on PyImport_ImportModuleNoBlock("time")
Normally, this should complete without error. However, we have experienced transient and occasional failures
There is a test for what happens in a background thread when the import lock is held by the main thread
"""

import threading
import imp
import sys
import datetime
import unittest

if sys.platform.startswith('win'):
    try:
        import win32api
    except ImportError:
        win32api = None
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

def use_cpu(n, symbol, finish_early_event=None):
    a = 3
    for i in range(n):
        a = 3 * a
        if i % 10000 == 0:
            sys.stdout.write(symbol)
        if finish_early_event is not None and finish_early_event.is_set():
            return

def win32_get_local_datetime():
    t = win32api.GetLocalTime()
    return datetime.datetime(t[0], t[1], t[3], t[4], t[5], t[6], t[7]*1000)

def win32_get_utc_datetime():
    t = win32api.GetSystemTime()
    return datetime.datetime(t[0], t[1], t[3], t[4], t[5], t[6], t[7]*1000)

def unix_get_local_datetime():
    t = timeval()
    if libc.gettimeofday(t, None) == 0:
        return datetime.datetime.fromtimestamp(float(t.seconds)+(t.microseconds/1000000.), None)
    raise ValueError("Error retrieving time")

def unix_get_utc_datetime():
    t = timeval()
    if libc.gettimeofday(t, None) == 0:
        libc.tzset()
        utc_offset = (ctypes.c_int32).in_dll(libc, 'timezone')
        return datetime.datetime.fromtimestamp(float(t.seconds)+(t.microseconds/1000000.)+utc_offset, None)
    raise ValueError("Error retrieving time")

if sys.platform.startswith('win'):
    get_local_datetime, get_utc_datetime = win32_get_local_datetime, win32_get_utc_datetime
elif sys.platform.startswith('linux'):
    get_local_datetime, get_utc_datetime = unix_get_local_datetime, unix_get_utc_datetime

def check_unsafe_function(target):
    def checker(self, *args, **kwargs):
        self.unsafe_function_delay()
        try:
            self.check_function(target, *args, **kwargs)
            self.unsafe_function_raised(target, False)
        except Exception as e:
            self.unsafe_function_raised(target, e)
    return checker

class TestBaseCodeNoImportLock(unittest.TestCase):
    def setUp(self):
        self.previous_time_module = sys.modules.pop('time')

    def tearDown(self):
        sys.modules['time'] = self.previous_time_module

    def unsafe_function_delay(self):
        # use_cpu(20000, '+')
        sys.stdout.write('&' if 'time' in sys.modules else '/')

    def unsafe_function_raised(self, target, had_exception):
        """Used to indicate the result of the function"""
        if had_exception:
            sys.stderr.write("Could not run %s.%s: %s\n" % (type(self).__name__, target.func_name, had_exception))
        else:
            sys.stdout.write("Ran %s.%s successfully\n" % (type(self).__name__, target.func_name))
        return had_exception

    def check_function(self, target):
        sys.stdout.write("Testing %s" % target.func_name)
        target(self)
        sys.stdout.write('\n')

    @check_unsafe_function
    def test_wrap_strftime(self):
        self.assertEquals(datetime.date(2020, 02, 20).strftime('%Y-%m-%d'), '2020-02-20')
        self.assertEquals(datetime.datetime(2020,02,20,20,20,20).strftime('%Y-%m-%d %H:%M:%S'), '2020-02-20 20:20:20')
        self.assertEquals(datetime.time(20, 20, 20).strftime('%H:%M:%S'), '20:20:20')

    @check_unsafe_function
    def test_time_time(self):
        today = datetime.date.today()
        now = datetime.datetime.now(); win32_now = get_local_datetime()
        utcnow = datetime.datetime.utcnow(); win32_utcnow = get_utc_datetime()
        assert today == win32_now.date()
        now_delta = win32_now - now
        utcnow_delta = win32_utcnow - utcnow
        assert now_delta.days == 0
        assert utcnow_delta.days == 0
        assert (now_delta.seconds*1000000 + now_delta.microseconds) <= 50000
        assert (utcnow_delta.seconds*1000000 + utcnow_delta.microseconds) <= 50000

    @check_unsafe_function
    def test_build_struct_time(self):
        self.assertEquals(datetime.date(2020, 02, 20).timetuple(), (2020, 02, 20, 0, 0, 0, 3, 51, -1))
        self.assertEquals(datetime.datetime(2020, 02, 20, 20, 20, 20).timetuple(), (2020, 02, 20, 20, 20, 20, 3, 51, -1))
        self.assertEquals(datetime.datetime(2020, 02, 20, 20, 20, 20).utctimetuple(), (2020, 02, 20, 20, 20, 20, 3, 51, 0))

    @check_unsafe_function
    def test_datetime_strptime(self):
        d = datetime.datetime.strptime('2020-02-20 20:20:20', '%Y-%m-%d %H:%M:%S')
        self.assertEquals(d.year, 2020)
        self.assertEquals(d.month, 02)
        self.assertEquals(d.day, 20)
        self.assertEquals(d.hour, 20)
        self.assertEquals(d.minute, 20)
        self.assertEquals(d.second, 20)

class TestBaseCodeWhenImportLockHeld(TestBaseCodeNoImportLock):
    def check_function(self, target):
        print("Testing %s" % target.func_name)
        complete_event = threading.Event()
        imp.acquire_lock()
        try:
            background_thread = threading.Thread(target=self.expect_import_error, name='background_lock_wanter', args=(target, complete_event))
            background_thread.start()
            use_cpu(100000, '.', complete_event) # this is like a timeout without using time.sleep
        finally:
            imp.release_lock()
        sys.stdout.write('\n')
        background_thread.join(timeout=10)
        assert self.background_result and isinstance(self.background_result, ImportError)

    def expect_import_error(self, target, complete_event=None):
        try:
            target(self)
            self.unsafe_function_raised(target, False)
        except Exception as e:
            self.unsafe_function_raised(target, e)
        if complete_event:
            complete_event.set()

    def unsafe_function_raised(self, target, had_exception):
        self.background_result = TestBaseCodeNoImportLock.unsafe_function_raised(self, target, had_exception)


if __name__ == '__main__':
    unittest.main()


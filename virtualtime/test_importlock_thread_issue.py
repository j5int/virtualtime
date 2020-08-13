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
from alt_time_funcs import alt_get_local_datetime, alt_get_utc_datetime
import virtualtime

def use_cpu(n, symbol, finish_early_event=None):
    a = 3
    for i in range(n):
        a = 3 * a
        if i % 10000 == 0:
            sys.stdout.write(symbol)
        if finish_early_event is not None and finish_early_event.is_set():
            return

def check_unsafe_function(target):
    def checker(self, *args, **kwargs):
        self.unsafe_function_delay()
        self.check_import_error_matches_expectation(target, *args, **kwargs)
    return checker

class TestBaseCodeNoImportLock(unittest.TestCase):
    date_cls = datetime.date
    datetime_cls = virtualtime._underlying_datetime_type
    time_cls = datetime.time

    expect_import_error = False

    def setUp(self):
        self.previous_time_module = sys.modules.pop('time', None)
        self.previous_strptime_module = sys.modules.pop('_strptime', None)

    def tearDown(self):
        if self.previous_time_module is not None:
            sys.modules['time'] = self.previous_time_module
        if self.previous_strptime_module is not None:
            sys.modules['_strptime'] = self.previous_strptime_module

    def unsafe_function_delay(self):
        use_cpu(20000, '+')
        if 'time' in sys.modules:
            sys.stderr.write('sys.modules has time module, unexpectedly... ')


    def log_function_result(self, target, had_exception):
        """Used to indicate the result of the function"""
        if had_exception:
            if self.expect_import_error and isinstance(had_exception, ImportError):
                sys.stdout.write('%s.%s had ImportError, as expected\n' % (type(self).__name__, target.func_name))
            elif not self.expect_import_error and isinstance(had_exception, ImportError):
                sys.stderr.write("%s.%s had unexpected ImportError: %s\n" % (type(self).__name__, target.func_name, had_exception))
            else:
                sys.stderr.write("Could not run %s.%s: %r\n" % (type(self).__name__, target.func_name, had_exception))
        else:
            if self.expect_import_error:
                sys.stderr.write("Ran %s.%s successfully, but expected ImportError\n" % (type(self).__name__, target.func_name))
            else:
                sys.stdout.write("Ran %s.%s successfully\n" % (type(self).__name__, target.func_name))
        return had_exception

    def check_import_error_matches_expectation(self, target, complete_event=None):
        sys.stdout.write("Testing %s: " % target.func_name)
        try:
            target(self)
            self.log_function_result(target, False)
        except Exception as e:
            self.log_function_result(target, e)
            if complete_event:
                complete_event.set()
            if not self.expect_import_error:
                raise
        if complete_event:
            complete_event.set()

    @check_unsafe_function
    def test_wrap_strftime_on_date(self):
        self.assertEquals(self.date_cls(2020, 02, 20).strftime('%Y-%m-%d'), '2020-02-20')

    @check_unsafe_function
    def test_wrap_strftime_on_datetime(self):
        self.assertEquals(self.datetime_cls(2020,02,20,20,20,20).strftime('%Y-%m-%d %H:%M:%S'), '2020-02-20 20:20:20')

    @check_unsafe_function
    def test_wrap_strftime_on_time(self):
        self.assertEquals(self.time_cls(20, 20, 20).strftime('%H:%M:%S'), '20:20:20')

    # the tests for today, now, and utcnow are separate because they can themselves import time as a side-effect
    @check_unsafe_function
    def test_time_time_today(self):
        # we don't actually patch this function currently
        today = self.date_cls.today()
        win32_now = alt_get_local_datetime()
        self.assertEqual(today, win32_now.date())

    @check_unsafe_function
    def test_time_time_now(self):
        now = self.datetime_cls.now()
        win32_now = alt_get_local_datetime()
        now_delta = win32_now - now
        assert now_delta.days == 0
        assert (now_delta.seconds*1000000 + now_delta.microseconds) <= 50000

    @check_unsafe_function
    def test_time_time_utcnow(self):
        utcnow = self.datetime_cls.utcnow()
        win32_utcnow = alt_get_utc_datetime()
        utcnow_delta = win32_utcnow - utcnow
        assert utcnow_delta.days == 0
        assert (utcnow_delta.seconds * 1000000 + utcnow_delta.microseconds) <= 50000

    @check_unsafe_function
    def test_build_struct_time_on_date(self):
        self.assertEquals(self.date_cls(2020, 02, 20).timetuple(), (2020, 02, 20, 0, 0, 0, 3, 51, -1))

    @check_unsafe_function
    def test_build_struct_time_on_datetime(self):
        self.assertEquals(self.datetime_cls(2020, 02, 20, 20, 20, 20).timetuple(), (2020, 02, 20, 20, 20, 20, 3, 51, -1))

    @check_unsafe_function
    def test_build_struct_time_on_datetime_utc(self):
        self.assertEquals(self.datetime_cls(2020, 02, 20, 20, 20, 20).utctimetuple(), (2020, 02, 20, 20, 20, 20, 3, 51, 0))

    @check_unsafe_function
    def test_datetime_strptime(self):
        # Note: this currently doesn't actually raise an ImportError even if import lock is held, and manages to import _strptime anyway
        # there is special code in TestBaseCodeWhenImportLockHeld to account for that
        d = self.datetime_cls.strptime('2020-02-20 20:20:20', '%Y-%m-%d %H:%M:%S')
        self.assertEquals(d.year, 2020)
        self.assertEquals(d.month, 02)
        self.assertEquals(d.day, 20)
        self.assertEquals(d.hour, 20)
        self.assertEquals(d.minute, 20)
        self.assertEquals(d.second, 20)

class TestBaseCodeWhenImportLockHeld(TestBaseCodeNoImportLock):
    expect_import_error = True
    def check_import_error_matches_expectation(self, target, complete_event=None):
        complete_event = threading.Event()
        imp.acquire_lock()
        try:
            background_thread = threading.Thread(target=TestBaseCodeNoImportLock.check_import_error_matches_expectation,
                                                 name='background_lock_wanter', args=(self, target, complete_event))
            background_thread.start()
            use_cpu(500000, '.', complete_event) # this is like a timeout without using time.sleep
        finally:
            imp.release_lock()
        sys.stdout.write('\n')
        background_thread.join(timeout=10)
        if self.expect_import_error:
            if target.func_name == 'test_datetime_strptime':
                if not isinstance(self.background_result, ImportError):
                    print("test_datetime_strptime didn't raise ImportError, but that is what we have grown to expect")
                else:
                    print("test_datetime_strptime did raise ImportError - no matter")
            else:
                assert self.background_result and isinstance(self.background_result, ImportError)
        else:
            self.assertFalse(self.background_result)


    def log_function_result(self, target, had_exception):
        self.background_result = TestBaseCodeNoImportLock.log_function_result(self, target, had_exception)


class TestVirtualTimeBaseCodeWhenImportLockHeld(TestBaseCodeWhenImportLockHeld):
    date_cls = virtualtime.date
    datetime_cls = virtualtime.datetime
    time_cls = virtualtime.time_no_importerror

    expect_import_error = False


class TestVirtualTimeVirtualCodeWhenImportLockHeld2(TestVirtualTimeBaseCodeWhenImportLockHeld):
    datetime_cls = virtualtime.virtual_datetime


if __name__ == '__main__':
    unittest.main()


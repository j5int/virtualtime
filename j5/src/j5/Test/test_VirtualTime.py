#!/usr/bin/env python

from j5.Test import VirtualTime
from j5.OS import datetime_tz
import datetime
import time
import pickle
import os
import subprocess
import sys

def outside(code_str, *import_modules):
    """Runs a code string in a separate process, pickles the result, and returns it"""
    import_modules_str = 'import %s' % ', '.join(import_modules) if import_modules else ''
    command_string = 'import sys, pickle; sys.path = pickle.loads(sys.stdin.read()); %s; sys.stdout.write(pickle.dumps(%s))' % (import_modules_str, code_str)
    pickle_path = pickle.dumps(sys.path)
    p = subprocess.Popen([sys.executable, "-c", command_string], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=os.environ)
    results, errors = p.communicate(pickle_path)
    if errors and errors.strip():
        raise ValueError(errors)
    return pickle.loads(results)

def run_time_function_test(time_function, set_function, diff):
    """Generic test for time_function and a set_function that can move the return of that time_function forwards or backwards by diff"""
    first_time = time_function()
    set_function(first_time + diff)
    late_time = time_function()
    set_function(first_time - diff)
    early_time = time_function()
    VirtualTime.real_time()
    last_time = time_function()
    assert early_time < first_time < last_time < late_time

def test_real_time():
    """tests that real time is still happening in the time module"""
    first_time = time.time()
    outside_time = outside("time.time()", "time")
    second_time = time.time()
    assert first_time < outside_time < second_time

def test_real_datetime_now():
    """tests that real time is still happening in the datetime module"""
    first_time = datetime.datetime.now()
    outside_time = outside("datetime.datetime.now()", "datetime")
    second_time = datetime.datetime.now()
    assert first_time < outside_time < second_time

def test_real_datetime_tz_now():
    """tests that real time is still happening in the datetime_tz module"""
    first_time = datetime_tz.datetime_tz.now()
    outside_time = outside("j5.OS.datetime_tz.datetime_tz.now()", "j5.OS.datetime_tz")
    second_time = datetime_tz.datetime_tz.now()
    assert first_time < outside_time < second_time

def test_virtual_time():
    """tests that we can set time"""
    run_time_function_test(time.time, VirtualTime.set_time, 100)

def test_virtual_datetime_now():
    """tests that setting time and datetime are both possible"""
    set_datetime = lambda new_time: VirtualTime.set_time(VirtualTime.local_datetime_to_time(new_time))
    run_time_function_test(datetime.datetime.now, set_datetime, datetime.timedelta(seconds=100))

def test_virtual_datetime_utcnow():
    """tests that setting time and datetime are both possible"""
    set_datetime = lambda new_time: VirtualTime.set_time(VirtualTime.utc_datetime_to_time(new_time))
    run_time_function_test(datetime.datetime.utcnow, set_datetime, datetime.timedelta(seconds=100))

def test_virtual_datetime_tz_now():
    """tests that setting time and datetime are both possible"""
    set_datetime = lambda new_time: VirtualTime.set_time(VirtualTime.local_datetime_to_time(new_time))
    run_time_function_test(datetime_tz.datetime_tz.now, set_datetime, datetime.timedelta(seconds=100))

def test_virtual_datetime_tz_utcnow():
    """tests that setting time and datetime are both possible"""
    set_datetime = lambda new_time: VirtualTime.set_time(VirtualTime.utc_datetime_to_time(new_time))
    run_time_function_test(datetime_tz.datetime_tz.utcnow, set_datetime, datetime.timedelta(seconds=100))



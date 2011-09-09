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

def check_real_time_function(time_function, code_str, *import_modules):
    """Generic test for a linear time function that can be run by a spawned python process too"""
    first_time = time_function()
    time.sleep(0.1)
    outside_time = outside(code_str, *import_modules)
    time.sleep(0.1)
    second_time = time_function()
    assert first_time < outside_time < second_time

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

def run_time_derived_function_test(derived_function, time_function, set_function, diff, min_diff=None):
    """Generic test for time_function and a set_function that can move the return of that time_function forwards or backwards by diff"""
    first_derived, first_time = derived_function(), time_function()
    set_function(first_time + diff)
    late_derived = derived_function()
    set_function(first_time - diff)
    early_derived = derived_function()
    VirtualTime.real_time()
    if min_diff:
        time.sleep(min_diff)
    last_derived = derived_function()
    assert early_derived < first_derived < last_derived < late_derived

def test_real_time():
    """tests that real time is still happening in the time.time() function"""
    check_real_time_function(time.time, "time.time()", "time")

def test_real_datetime_now():
    """tests that real time is still happening in the datetime module"""
    check_real_time_function(datetime.datetime.now, "datetime.datetime.now()", "datetime")

def test_real_datetime_tz_now():
    """tests that real time is still happening in the datetime_tz module"""
    check_real_time_function(datetime_tz.datetime_tz.now, "j5.OS.datetime_tz.datetime_tz.now()", "j5.OS.datetime_tz")

def test_virtual_time():
    """tests that we can set time"""
    run_time_function_test(time.time, VirtualTime.set_time, 100)

def test_virtual_localtime():
    """tests that we can set time and it affects localtime"""
    run_time_derived_function_test(time.localtime, time.time, VirtualTime.set_time, 100, min_diff=1)

def test_virtual_gmtime():
    """tests that we can set time and it affects gmtime"""
    run_time_derived_function_test(time.gmtime, time.time, VirtualTime.set_time, 100, min_diff=1)

# TODO: handle strings not necessarily being increasing on time

def test_virtual_asctime():
    """tests that we can set time and it affects asctime"""
    run_time_derived_function_test(time.asctime, time.time, VirtualTime.set_time, 100, min_diff=1)

def test_virtual_ctime():
    """tests that we can set time and it affects ctime"""
    run_time_derived_function_test(time.ctime, time.time, VirtualTime.set_time, 100, min_diff=1)

def test_virtual_strftime():
    """tests that we can set time and it affects ctime"""
    strftime_iso = lambda: time.strftime("%Y-%m-%d %H:%M:%S")
    run_time_derived_function_test(strftime_iso, time.time, VirtualTime.set_time, 100, min_diff=1)

def test_virtual_datetime_now():
    """tests that setting time and datetime are both possible"""
    run_time_function_test(datetime.datetime.now, VirtualTime.set_local_datetime, datetime.timedelta(seconds=100))

def test_virtual_datetime_utcnow():
    """tests that setting time and datetime are both possible"""
    run_time_function_test(datetime.datetime.utcnow, VirtualTime.set_utc_datetime, datetime.timedelta(seconds=100))

def test_virtual_datetime_tz_now():
    """tests that setting time and datetime are both possible"""
    run_time_function_test(datetime_tz.datetime_tz.now, VirtualTime.set_local_datetime, datetime.timedelta(seconds=100))

def test_virtual_datetime_tz_utcnow():
    """tests that setting time and datetime are both possible"""
    run_time_function_test(datetime_tz.datetime_tz.utcnow, VirtualTime.set_utc_datetime, datetime.timedelta(seconds=100))



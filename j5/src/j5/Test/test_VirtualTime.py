#!/usr/bin/env python

from j5.Test import VirtualTime
from j5.OS import datetime_tz
import datetime
import time
import pytz
import pickle
import os
import subprocess
import sys
import decorator
import threading

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

@decorator.decorator
def restore_time_after(test_function, *args, **kwargs):
    try:
        return test_function(*args, **kwargs)
    finally:
        VirtualTime.restore_time()

@restore_time_after
def check_real_time_function(time_function, code_str, *import_modules):
    """Generic test for a linear time function that can be run by a spawned python process too"""
    first_time = time_function()
    time.sleep(0.1)
    outside_time = outside(code_str, *import_modules)
    time.sleep(0.1)
    second_time = time_function()
    assert first_time < outside_time < second_time

@restore_time_after
def run_time_function_test(time_function, set_function, diff):
    """Generic test for time_function and a set_function that can move the return of that time_function forwards or backwards by diff"""
    first_time = time_function()
    set_function(first_time + diff)
    late_time = time_function()
    set_function(first_time - diff)
    early_time = time_function()
    VirtualTime.restore_time()
    last_time = time_function()
    assert early_time < first_time < last_time < late_time

@restore_time_after
def run_time_derived_function_test(derived_function, time_function, set_function, diff, min_diff=None):
    """Generic test for time_function and a set_function that can move the return of that time_function forwards or backwards by diff"""
    first_derived, first_time = derived_function(), time_function()
    set_function(first_time + diff)
    late_derived = derived_function()
    set_function(first_time - diff)
    early_derived = derived_function()
    VirtualTime.restore_time()
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

def order_preserving_timestr_reslice(s):
    """Changes the Python format for asctime/ctime 'Sat Jun 06 16:26:11 1998' to '1998-06-06 16:26:11' so that it always increases over time"""
    month_table = "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    s = s.replace(" ", "0")
    y, m, d, t = int(s[-4:]), month_table.index(s[4:7]), int(s[8:10]), s[11:19]
    return "%04d-%02d-%02d %s" % (y, m, d, t)

def test_virtual_asctime():
    """tests that we can set time and it affects asctime"""
    order_preserving_asctime = lambda: order_preserving_timestr_reslice(time.asctime())
    run_time_derived_function_test(order_preserving_asctime, time.time, VirtualTime.set_time, 100, min_diff=1)

def test_virtual_ctime():
    """tests that we can set time and it affects ctime"""
    order_preserving_ctime = lambda: order_preserving_timestr_reslice(time.ctime())
    run_time_derived_function_test(order_preserving_ctime, time.time, VirtualTime.set_time, 100, min_diff=1)

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

def test_virtual_datetime_tz_now_other_tz():
    """tests that setting time and datetime are both possible"""
    for tz_name in ["Asia/Tokyo", "Europe/London", "America/Chicago"]:
        tz = pytz.timezone(tz_name)
        tz_now = lambda: datetime_tz.datetime_tz.now().astimezone(tz)
        run_time_derived_function_test(tz_now, datetime_tz.datetime_tz.utcnow, VirtualTime.set_utc_datetime, datetime.timedelta(seconds=100))

def test_sleep():
    """Tests that sleep comes back quicker than normal when time is advanced"""
    first_time = time.time()
    sleeper_thread = threading.Thread(target=time.sleep, args=(15,), name="test_sleep_sleeper")
    sleeper_thread.start()
    VirtualTime.set_time(first_time + 20)
    sleeper_thread.join()
    VirtualTime.restore_time()
    join_time = time.time()
    assert join_time - first_time < 0.5


#!/usr/bin/env python

from j5.Test import VirtualTime
from j5.Test import Utils
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
import logging

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
def run_time_function_test(time_function, set_function, diff, enabled=True):
    """Generic test for time_function and a set_function that can move the return of that time_function forwards or backwards by diff
    Checks that the right thing will happen when VirtualTime enabled/disabled"""
    first_time = time_function()
    set_function(first_time + diff)
    late_time = time_function()
    set_function(first_time - diff)
    early_time = time_function()
    VirtualTime.restore_time()
    last_time = time_function()
    if enabled:
        assert early_time < first_time < last_time < late_time
    else:
        assert first_time <= late_time <= early_time <= last_time

@restore_time_after
def run_time_derived_function_test(derived_function, time_function, set_function, diff, min_diff=None, enabled=True):
    """Generic test for time_function and a set_function that can move the return of that time_function forwards or backwards by diff
    Checks that the right thing will happen when VirtualTime enabled/disabled"""
    first_derived, first_time = derived_function(), time_function()
    set_function(first_time + diff)
    late_derived = derived_function()
    set_function(first_time - diff)
    early_derived = derived_function()
    VirtualTime.restore_time()
    if min_diff:
        time.sleep(min_diff)
    last_derived = derived_function()
    if enabled:
        assert early_derived < first_derived < last_derived < late_derived
    else:
        assert first_derived <= late_derived <= early_derived <= last_derived

def order_preserving_timestr_reslice(s):
    """Changes the Python format for asctime/ctime 'Sat Jun 06 16:26:11 1998' to '1998-06-06 16:26:11' so that it always increases over time"""
    month_table = "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    s = s.replace(" ", "0")
    y, m, d, t = int(s[-4:]), month_table.index(s[4:7]), int(s[8:10]), s[11:19]
    return "%04d-%02d-%02d %s" % (y, m, d, t)

class RunUnpatched(object):
    """Base class for tests that should all be run with VirtualTime disabled"""
    @classmethod
    def setup_class(cls):
        """Ensure that VirtualTime is disabled when running these tests"""
        cls.virtual_time_enabled = VirtualTime.enabled()
        assert not VirtualTime.enabled()

    @classmethod
    def teardown_class(cls):
        """Ensure that VirtualTime is disabled after running these tests"""
        del cls.virtual_time_enabled
        assert not VirtualTime.enabled()

class RunPatched(object):
    """Base class for tests that should all be run with VirtualTime enabled"""
    @classmethod
    def setup_class(cls):
        """Ensure that VirtualTime is disabled before, then enabled when running these tests"""
        assert not VirtualTime.enabled()
        VirtualTime.enable()
        cls.virtual_time_enabled = VirtualTime.enabled()
        assert cls.virtual_time_enabled

    @classmethod
    def teardown_class(cls):
        """Ensure that VirtualTime was enabled when running these tests, but disabled after"""
        del cls.virtual_time_enabled
        assert VirtualTime.enabled()
        VirtualTime.disable()
        assert not VirtualTime.enabled()

    def setup_method(self, method):
        """Restores normal time to ensure tests start cleanly"""
        VirtualTime.restore_time()

    def teardown_method(self, method):
        """Restores normal time after the method has finished"""
        VirtualTime.restore_time()

class RealTimeBase(object):
    """Tests for real time functions"""
    def test_time(self):
        """tests that real time is still happening in the time.time() function"""
        check_real_time_function(time.time, "time.time()", "time")

    def test_datetime_now(self):
        """tests that real time is still happening in the datetime module"""
        check_real_time_function(datetime.datetime.now, "datetime.datetime.now()", "datetime")

    def test_datetime_utcnow(self):
        """tests that real time is still happening in the datetime module"""
        check_real_time_function(datetime.datetime.utcnow, "datetime.datetime.utcnow()", "datetime")

    def test_datetime_tz_now(self):
        """tests that real time is still happening in the datetime_tz module"""
        check_real_time_function(datetime_tz.datetime_tz.now, "j5.OS.datetime_tz.datetime_tz.now()", "j5.OS.datetime_tz")

    def test_datetime_tz_utcnow(self):
        """tests that real time is still happening in the datetime_tz module"""
        check_real_time_function(datetime_tz.datetime_tz.utcnow, "j5.OS.datetime_tz.datetime_tz.utcnow()", "j5.OS.datetime_tz")

class TestUnpatchedRealTime(RealTimeBase, RunUnpatched):
    """Tests for real time functions when VirtualTime is disabled"""

class TestPatchedRealTime(RealTimeBase, RunPatched):
    """Tests for real time functions when VirtualTime is enabled"""

class TestTimeNotification(RunPatched):
    """Tests the different notification events that happen when VirtualTime is adjusted"""
    def test_notify_on_change(self):
        self.notify_event = threading.Event()
        VirtualTime.notify_on_change(self.notify_event)
        start_time = VirtualTime._original_time()
        VirtualTime.set_offset(1)
        assert self.notify_event.wait(0.1)
        self.notify_event.clear()
        offset_time = VirtualTime._original_time()
        assert offset_time - start_time < 0.1
        VirtualTime.set_time(0)
        assert self.notify_event.wait(0.1)
        self.notify_event.clear()
        set_time = VirtualTime._original_time()
        assert set_time - offset_time < 0.1
        VirtualTime.restore_time()
        assert self.notify_event.wait(0.1)
        self.notify_event.clear()
        restore_time = VirtualTime._original_time()
        assert restore_time - set_time < 0.1

    def callback_thread(self):
        """Repeatedly sets the target event whilst recording the offsets"""
        while not self.callback_stop:
            if self.notify_event.wait(5):
                if self.callback_stop:
                    break
                self.callback_logs.append((VirtualTime._original_time(), VirtualTime._time_offset, self.callback_event.is_set()))
                self.notify_event.clear()
                self.callback_event.set()
            elif not self.callback_stop:
                self.callback_missed.append((VirtualTime._original_time(), VirtualTime._time_offset))

    def test_callback(self):
        self.notify_event = threading.Event()
        VirtualTime.notify_on_change(self.notify_event)
        self.callback_stop = False
        self.callback_event = threading.Event()
        self.callback_logs = []
        self.callback_missed = []
        ct = threading.Thread(target=self.callback_thread)
        ct.start()
        VirtualTime.wait_for_callback_on_change(self.callback_event)
        try:
            start_time = VirtualTime._original_time()
            VirtualTime.set_offset(1)
            assert len(self.callback_logs) == 1 and not self.callback_missed
            assert self.callback_logs[0][1:] == (1, False)
            offset_time = VirtualTime._original_time()
            assert offset_time - start_time < 0.1
            VirtualTime.set_time(0)
            assert len(self.callback_logs) == 2 and not self.callback_missed
            assert self.callback_logs[1][1] < -start_time + 1 and self.callback_logs[1][2] is False
            set_time = VirtualTime._original_time()
            assert set_time - offset_time < 0.1
            VirtualTime.restore_time()
            assert len(self.callback_logs) == 3 and not self.callback_missed
            assert self.callback_logs[1][1] < -start_time + 1 and self.callback_logs[1][2] is False
            restore_time = VirtualTime._original_time()
            assert restore_time - set_time < 0.1
        finally:
            # deleting this should ensure it drops out of the weak set and doesn't hang things up later...
            del self.callback_event
            self.callback_stop = True
            self.notify_event.set()
            ct.join()

class VirtualTimeBase(object):
    """Tests for virtual time functions when VirtualTime is enabled"""
    def test_time(self):
        """tests that we can set time"""
        run_time_function_test(time.time, VirtualTime.set_time, 100, enabled=self.virtual_time_enabled)

    def test_localtime(self):
        """tests that we can set time and it affects localtime"""
        run_time_derived_function_test(time.localtime, time.time, VirtualTime.set_time, 100, min_diff=1, enabled=self.virtual_time_enabled)

    def test_gmtime(self):
        """tests that we can set time and it affects gmtime"""
        run_time_derived_function_test(time.gmtime, time.time, VirtualTime.set_time, 100, min_diff=1, enabled=self.virtual_time_enabled)

    def test_asctime(self):
        """tests that we can set time and it affects asctime"""
        order_preserving_asctime = lambda: order_preserving_timestr_reslice(time.asctime())
        run_time_derived_function_test(order_preserving_asctime, time.time, VirtualTime.set_time, 100, min_diff=1, enabled=self.virtual_time_enabled)

    def test_ctime(self):
        """tests that we can set time and it affects ctime"""
        order_preserving_ctime = lambda: order_preserving_timestr_reslice(time.ctime())
        run_time_derived_function_test(order_preserving_ctime, time.time, VirtualTime.set_time, 100, min_diff=1, enabled=self.virtual_time_enabled)

    def test_strftime(self):
        """tests that we can set time and it affects ctime"""
        strftime_iso = lambda: time.strftime("%Y-%m-%d %H:%M:%S")
        run_time_derived_function_test(strftime_iso, time.time, VirtualTime.set_time, 100, min_diff=1, enabled=self.virtual_time_enabled)

    def test_datetime_now(self):
        """tests that setting time and datetime are both possible"""
        run_time_function_test(datetime.datetime.now, VirtualTime.set_local_datetime, datetime.timedelta(seconds=100), enabled=self.virtual_time_enabled)

    def test_datetime_utcnow(self):
        """tests that setting time and datetime are both possible"""
        run_time_function_test(datetime.datetime.utcnow, VirtualTime.set_utc_datetime, datetime.timedelta(seconds=100), enabled=self.virtual_time_enabled)

    def test_datetime_tz_now(self):
        """tests that setting time and datetime are both possible"""
        run_time_function_test(datetime_tz.datetime_tz.now, VirtualTime.set_local_datetime, datetime.timedelta(seconds=100), enabled=self.virtual_time_enabled)

    def test_datetime_tz_utcnow(self):
        """tests that setting time and datetime are both possible"""
        run_time_function_test(datetime_tz.datetime_tz.utcnow, VirtualTime.set_utc_datetime, datetime.timedelta(seconds=100), enabled=self.virtual_time_enabled)

    def test_datetime_tz_now_other_tz(self):
        """tests that setting time and datetime are both possible"""
        for tz_name in ["Asia/Tokyo", "Europe/London", "America/Chicago"]:
            tz = pytz.timezone(tz_name)
            tz_now = lambda: datetime_tz.datetime_tz.now().astimezone(tz)
            run_time_derived_function_test(tz_now, datetime_tz.datetime_tz.utcnow, VirtualTime.set_utc_datetime, datetime.timedelta(seconds=100), enabled=self.virtual_time_enabled)

class TestDisabledVirtualTime(VirtualTimeBase, RunUnpatched):
    """Tests that virtual time functions have no effect when VirtualTime is disabled"""

class TestVirtualTime(VirtualTimeBase, RunPatched):
    """Tests that virtual time functions have no effect when VirtualTime is disabled"""

class SleepBase(object):
    def setup_method(self, method):
        self.initial_waiter_count = len(VirtualTime._virtual_time_state._Condition__waiters)

    def teardown_method(self, method):
        del self.initial_waiter_count

    def wait_sleep_started(self, sleep_count, max_wait=5.0):
        """Waits for the given number of sleeps to start before continuing (with a timeout)"""
        if not self.virtual_time_enabled:
            return
        start_wait_check = VirtualTime._original_time()
        while len(VirtualTime._virtual_time_state._Condition__waiters) < self.initial_waiter_count + sleep_count:
            VirtualTime._original_sleep(0.001)
            delay = VirtualTime._original_time() - start_wait_check
            if delay > max_wait:
                raise ValueError("Not enough sleepers started waiting in time...")

    @restore_time_after
    def test_sleep(self):
        """Tests that sleep comes back quicker than normal when time is advanced"""
        first_time = time.time()
        sleeper_thread = threading.Thread(target=time.sleep, args=(3,), name="test_sleep_sleeper")
        sleeper_thread.start()
        self.wait_sleep_started(1, 0.2)
        VirtualTime.set_time(first_time + 5)
        sleeper_thread.join()
        VirtualTime.restore_time()
        join_time = time.time()
        if self.virtual_time_enabled:
            assert join_time - first_time < 0.5
        else:
            assert join_time - first_time >= 3

    @restore_time_after
    def test_parallel_sleeps(self):
        """Tests that sleep comes back quicker than normal when time is advanced, and that this works with lots of threads"""
        first_time = VirtualTime._original_time()
        sleeper_threads = {}
        REPEATS = 100
        for n in range(REPEATS):
            sleeper_threads[n] = sleeper_thread = threading.Thread(target=time.sleep, args=(3,), name="test_sleep_sleeper_%d" % n)
            sleeper_thread.start()
        self.wait_sleep_started(REPEATS, 0.5)
        thread_time = VirtualTime._original_time()
        setup_duration = thread_time - first_time
        assert setup_duration < 0.1
        VirtualTime.set_time(thread_time + 20)
        for n in range(REPEATS):
            sleeper_threads[n].join()
        join_time = VirtualTime._original_time()
        sleep_duration = join_time - thread_time
        VirtualTime.restore_time()
        if self.virtual_time_enabled:
            assert sleep_duration < 0.2
        else:
            assert sleep_duration >= 3

class TestDisabledSleep(SleepBase, RunUnpatched):
    pass

class TestSleep(SleepBase, RunPatched):
    @Utils.if_long_test_run()
    def test_many_parallel_sleeps(self):
        """Tests that sleep comes back quicker than normal when time is advanced, and that this works with lots of threads when repeated many times"""
        LOOPS = 100
        for m in range(LOOPS):
            self.test_parallel_sleeps()

class TestFastForward(RunPatched):
    def fast_forward_catcher(self, event, msg_dict):
        offsets = msg_dict['offsets']
        while "stop" not in msg_dict:
            event.wait()
            offsets.append(VirtualTime._time_offset)
            event.clear()

    @restore_time_after
    def test_fast_forward_time(self):
        """Test that fast forwarding the time works properly"""
        event = threading.Event()
        VirtualTime.notify_on_change(event)
        offsets = []
        msg_dict = {'offsets': offsets}
        catcher_thread = threading.Thread(target=self.fast_forward_catcher, args=(event, msg_dict))
        catcher_thread.start()
        start_time = VirtualTime._original_time()
        VirtualTime.fast_forward_time(1)
        assert VirtualTime._time_offset == 1
        VirtualTime.fast_forward_time(2.5)
        assert VirtualTime._time_offset == 3.5
        VirtualTime.fast_forward_time(target=start_time + 9.1, step_size=2.0)
        assert 9 <= VirtualTime._time_offset <= 9.2
        VirtualTime.restore_time()
        VirtualTime.fast_forward_time(-1.3, step_size=0.9)
        VirtualTime.restore_time()
        msg_dict['stop'] = True
        event.set()
        catcher_thread.join()
        assert offsets[:6] == [1.0, 2.0, 3.0, 3.5, 5.5, 7.5]
        assert 9 <= offsets[6] <= 9.2
        assert offsets[7:] == [0, -0.9, -1.3, 0]

    @Utils.if_long_test_run()
    @restore_time_after
    def test_fast_forward_time_long(self):
        """Test that fast forwarding the time a long way works properly"""
        event = threading.Event()
        VirtualTime.notify_on_change(event)
        offsets = []
        msg_dict = {'offsets': offsets}
        catcher_thread = threading.Thread(target=self.fast_forward_catcher, args=(event, msg_dict))
        catcher_thread.start()
        start_time = VirtualTime._original_time()
        VirtualTime.fast_forward_time(1000, step_size=1)
        VirtualTime.restore_time()
        msg_dict['stop'] = True
        event.set()
        catcher_thread.join()
        assert offsets == range(1, 1001) + [0]

    @restore_time_after
    def test_fast_forward_datetime_style(self):
        """Test that fast forwarding the time works properly when using datetime-style objects"""
        event = threading.Event()
        VirtualTime.notify_on_change(event)
        offsets = []
        msg_dict = {'offsets': offsets}
        catcher_thread = threading.Thread(target=self.fast_forward_catcher, args=(event, msg_dict))
        catcher_thread.start()
        start_time = VirtualTime._original_datetime_now()
        utc_start_time = datetime_tz.localize(start_time).astimezone(pytz.utc)
        VirtualTime.fast_forward_timedelta(datetime.timedelta(seconds=1))
        assert VirtualTime._time_offset == 1
        VirtualTime.fast_forward_timedelta(datetime.timedelta(seconds=2.5))
        assert VirtualTime._time_offset == 3.5
        VirtualTime.fast_forward_local_datetime(target=start_time + datetime.timedelta(seconds=9.1), step_size=datetime.timedelta(seconds=2.0))
        assert 9 <= VirtualTime._time_offset <= 9.2
        VirtualTime.fast_forward_utc_datetime(target=utc_start_time + datetime.timedelta(seconds=18.2), step_size=datetime.timedelta(seconds=20.0))
        assert 18 <= VirtualTime._time_offset <= 18.3
        VirtualTime.restore_time()
        VirtualTime.fast_forward_timedelta(datetime.timedelta(seconds=-1.3), step_size=datetime.timedelta(seconds=0.9))
        VirtualTime.restore_time()
        msg_dict['stop'] = True
        event.set()
        catcher_thread.join()
        assert offsets[:6] == [1.0, 2.0, 3.0, 3.5, 5.5, 7.5]
        assert 9 <= offsets[6] <= 9.2
        assert 18 <= offsets[7] <= 18.3
        assert offsets[8:] == [0, -0.9, -1.3, 0]

    def fast_forward_delayer(self, notify_event, delay_event, msg_dict):
        offsets = msg_dict['offsets']
        positions = msg_dict['positions']
        while "stop" not in msg_dict:
            notify_event.wait()
            offsets.append(VirtualTime._time_offset)
            position = positions.pop(0) if positions else ""
            if position == "start_job":
                VirtualTime.delay_fast_forward_until_set(delay_event)
                VirtualTime._original_sleep(0.1)
                delay_event.set()
            notify_event.clear()

    @restore_time_after
    def test_fast_forward_delay(self):
        """Test that fast forwarding the time works properly"""
        notify_event = threading.Event()
        VirtualTime.notify_on_change(notify_event)
        delay_event = threading.Event()
        offsets = []
        positions = ["start_job", ""]
        msg_dict = {'offsets': offsets, 'positions': positions}
        catcher_thread = threading.Thread(target=self.fast_forward_delayer, args=(notify_event, delay_event, msg_dict))
        catcher_thread.start()
        start_time = VirtualTime._original_time()
        VirtualTime.fast_forward_time(2)
        assert VirtualTime._time_offset == 2
        VirtualTime.restore_time()
        msg_dict['stop'] = True
        notify_event.set()
        catcher_thread.join()
        completion_time = VirtualTime._original_time()
        assert offsets == [1.0, 2.0, 0]
        assert completion_time - start_time < 0.2
        assert delay_event.is_set()

class TestInheritance(object):
    """Tests how detection of inheritance works for datetime classes"""
    def setup_method(self, method):
        """Ensure that VirtualTime is disabled when starting each test"""
        VirtualTime.disable()
        assert not VirtualTime.enabled()

    def teardown_method(self, method):
        """Ensure that VirtualTime is disabled after running each test"""
        VirtualTime.disable()
        assert not VirtualTime.enabled()

    def test_disabled(self):
        VirtualTime.disable()
        assert issubclass(datetime_tz.datetime_tz, datetime.datetime)

    def test_enabled(self):
        VirtualTime.enable()
        assert issubclass(datetime_tz.datetime_tz, datetime.datetime)

    def test_switching(self):
        orig_datetime = datetime.datetime
        class derived_datetime(datetime.datetime):
            pass
        assert issubclass(datetime_tz.datetime_tz, orig_datetime)
        assert issubclass(datetime_tz.datetime_tz, datetime.datetime)
        assert issubclass(derived_datetime, orig_datetime)
        assert issubclass(derived_datetime, datetime.datetime)
        VirtualTime.enable()
        class derived_datetime2(datetime.datetime):
            pass
        assert issubclass(datetime_tz.datetime_tz, orig_datetime)
        assert issubclass(datetime_tz.datetime_tz, datetime.datetime)
        assert issubclass(derived_datetime, orig_datetime)
        assert issubclass(derived_datetime, datetime.datetime)
        assert issubclass(derived_datetime2, orig_datetime)
        assert issubclass(derived_datetime2, datetime.datetime)
        VirtualTime.disable()
        assert issubclass(datetime_tz.datetime_tz, orig_datetime)
        assert issubclass(datetime_tz.datetime_tz, datetime.datetime)
        assert issubclass(derived_datetime, orig_datetime)
        assert issubclass(derived_datetime, datetime.datetime)
        assert issubclass(derived_datetime2, orig_datetime)
        assert issubclass(derived_datetime2, datetime.datetime)

    def test_switching_values(self):
        now = datetime_tz.datetime_tz.now()
        assert isinstance(now, datetime.datetime)
        VirtualTime.enable()
        now = datetime_tz.datetime_tz.now()
        assert isinstance(now, datetime.datetime)


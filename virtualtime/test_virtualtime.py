#!/usr/bin/env python

import virtualtime
from virtualtime import datetime_tz
from virtualtime.datetime_tz import test_datetime_tz
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
import datetime
from nose.plugins.attrib import attr


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
        virtualtime.restore_time()

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
def run_time_function_tst(time_function, set_function, diff, enabled=True):
    """Generic test for time_function and a set_function that can move the return of that time_function forwards or backwards by diff
    Checks that the right thing will happen when virtualtime enabled/disabled"""
    first_time = time_function()
    set_function(first_time + diff)
    late_time = time_function()
    set_function(first_time - diff)
    early_time = time_function()
    virtualtime.restore_time()
    last_time = time_function()
    if enabled:
        assert early_time < first_time < last_time < late_time
    else:
        assert first_time <= late_time <= early_time <= last_time

@restore_time_after
def run_time_derived_function_tst(derived_function, time_function, set_function, diff, min_diff=None, enabled=True):
    """Generic test for time_function and a set_function that can move the return of that time_function forwards or backwards by diff
    Checks that the right thing will happen when virtualtime enabled/disabled"""
    first_derived, first_time = derived_function(), time_function()
    set_function(first_time + diff)
    late_derived = derived_function()
    set_function(first_time - diff)
    early_derived = derived_function()
    virtualtime.restore_time()
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
    """Base class for tests that should all be run with virtualtime disabled"""
    @classmethod
    def setup_class(cls):
        """Ensure that virtualtime is disabled when running these tests"""
        cls.virtual_time_enabled = virtualtime.enabled()
        assert not virtualtime.enabled()

    @classmethod
    def teardown_class(cls):
        """Ensure that virtualtime is disabled after running these tests"""
        del cls.virtual_time_enabled
        assert not virtualtime.enabled()

class RunPatched(object):
    """Base class for tests that should all be run with virtualtime enabled"""
    @classmethod
    def setup_class(cls):
        """Ensure that virtualtime is disabled before, then enabled when running these tests"""
        assert not virtualtime.enabled()
        virtualtime.enable()
        cls.virtual_time_enabled = virtualtime.enabled()
        assert cls.virtual_time_enabled

    @classmethod
    def teardown_class(cls):
        """Ensure that virtualtime was enabled when running these tests, but disabled after"""
        del cls.virtual_time_enabled
        assert virtualtime.enabled()
        virtualtime.disable()
        assert not virtualtime.enabled()

    def setup_method(self, method):  # This is a wrapper of setUp for py.test (py.test and nose take different method setup methods)
        self.setUp()

    def setUp(self):
        """Restores normal time to ensure tests start cleanly"""
        virtualtime.restore_time()

    def teardown_method(self, method):  # This is a wrapper of tearDown for py.test (py.test and nose take different method setup methods)
        self.tearDown()

    def tearDown(self):
        """Restores normal time after the method has finished"""
        virtualtime.restore_time()

class TestPartialPatching(object):
    @classmethod
    def setup_class(cls):
        virtualtime.disable()

    def test_correspondence(self):
        """Checks that patching time and datetime modules independently works"""
        start_time, start_date = time.time(), datetime.datetime.now()
        virtualtime.patch_time_module()
        second_time, second_date = time.time(), datetime.datetime.now()
        assert 0 <= second_time - start_time <= 0.05
        assert datetime.timedelta(0) <= second_date - start_date <= datetime.timedelta(seconds=0.05)
        virtualtime.set_offset(3600)
        half_time, half_date = time.time(), datetime.datetime.now()
        assert 3600 <= half_time - start_time <= 3600.1
        # datetime is not patched yet
        assert datetime.timedelta(seconds=0) <= half_date - start_date <= datetime.timedelta(seconds=0.1)
        virtualtime.patch_datetime_module()
        whole_time, whole_date = time.time(), datetime.datetime.now()
        assert 3600 <= whole_time - start_time <= 3600.1
        assert datetime.timedelta(seconds=3600) <= whole_date - start_date <= datetime.timedelta(seconds=3600.1)
        virtualtime.unpatch_time_module()
        other_half_time, other_half_date = time.time(), datetime.datetime.now()
        assert 0 <= other_half_time - start_time <= 0.1
        assert datetime.timedelta(seconds=3600) <= other_half_date - start_date <= datetime.timedelta(seconds=3600.1)

    @classmethod
    def teardown_class(cls):
        virtualtime.disable()

class RealTimeBase(object):
    """Tests for real time functions"""
    def test_time(self):
        """tests that real time is still happening in the time.time() function"""
        check_real_time_function(time.time, "time.time()", "time")

    def test_datetime_now(self):
        """tests that real time is still happening in the datetime module"""
        check_real_time_function(datetime.datetime.now, "datetime.datetime.now()", "datetime")

    def test_datetime_now_with_tz(self):
        """tests that real time is still happening in the datetime module"""
        def f():
            return datetime.datetime.now(pytz.timezone('Africa/Johannesburg'))
        check_real_time_function(f, "datetime.datetime.now(pytz.timezone('Africa/Johannesburg'))", "datetime", "pytz")

    def test_datetime_utcnow(self):
        """tests that real time is still happening in the datetime module"""
        check_real_time_function(datetime.datetime.utcnow, "datetime.datetime.utcnow()", "datetime")

    def test_datetime_tz_now(self):
        """tests that real time is still happening in the datetime_tz module"""
        check_real_time_function(datetime_tz.datetime_tz.now, "virtualtime.datetime_tz.datetime_tz.now()", "virtualtime.datetime_tz")

    def test_datetime_tz_utcnow(self):
        """tests that real time is still happening in the datetime_tz module"""
        check_real_time_function(datetime_tz.datetime_tz.utcnow, "virtualtime.datetime_tz.datetime_tz.utcnow()", "virtualtime.datetime_tz")

class TestUnpatchedRealTime(RealTimeBase, RunUnpatched):
    """Tests for real time functions when virtualtime is disabled"""

class TestPatchedRealTime(RealTimeBase, RunPatched):
    """Tests for real time functions when virtualtime is enabled"""

class TestTimeNotification(RunPatched):
    """Tests the different notification events that happen when virtualtime is adjusted"""
    def test_notify_on_change(self):
        self.notify_event = threading.Event()
        virtualtime.notify_on_change(self.notify_event)
        start_time = virtualtime._original_time()
        virtualtime.set_offset(1)
        assert self.notify_event.wait(0.1)
        self.notify_event.clear()
        offset_time = virtualtime._original_time()
        assert offset_time - start_time < 0.1
        virtualtime.set_time(0)
        assert self.notify_event.wait(0.1)
        self.notify_event.clear()
        set_time = virtualtime._original_time()
        assert set_time - offset_time < 0.1
        virtualtime.restore_time()
        assert self.notify_event.wait(0.1)
        self.notify_event.clear()
        restore_time = virtualtime._original_time()
        assert restore_time - set_time < 0.1

    def callback_thread(self):
        """Repeatedly sets the target event whilst recording the offsets"""
        while not self.callback_stop:
            if self.notify_event.wait(5):
                if self.callback_stop:
                    break
                self.callback_logs.append((virtualtime._original_time(), virtualtime._time_offset, self.callback_event.is_set()))
                self.notify_event.clear()
                self.callback_event.set()
            elif not self.callback_stop:
                self.callback_missed.append((virtualtime._original_time(), virtualtime._time_offset))

    def test_callback(self):
        self.notify_event = threading.Event()
        virtualtime.notify_on_change(self.notify_event)
        self.callback_stop = False
        self.callback_event = threading.Event()
        self.callback_logs = []
        self.callback_missed = []
        ct = threading.Thread(target=self.callback_thread)
        ct.start()
        virtualtime.wait_for_callback_on_change(self.callback_event)
        try:
            start_time = virtualtime._original_time()
            virtualtime.set_offset(1)
            assert len(self.callback_logs) == 1 and not self.callback_missed
            assert self.callback_logs[0][1:] == (1, False)
            offset_time = virtualtime._original_time()
            assert offset_time - start_time < 0.1
            virtualtime.set_time(0)
            assert len(self.callback_logs) == 2 and not self.callback_missed
            assert self.callback_logs[1][1] < -start_time + 1 and self.callback_logs[1][2] is False
            set_time = virtualtime._original_time()
            assert set_time - offset_time < 0.1
            virtualtime.restore_time()
            assert len(self.callback_logs) == 3 and not self.callback_missed
            assert self.callback_logs[1][1] < -start_time + 1 and self.callback_logs[1][2] is False
            restore_time = virtualtime._original_time()
            assert restore_time - set_time < 0.1
        finally:
            # deleting this should ensure it drops out of the weak set and doesn't hang things up later...
            del self.callback_event
            self.callback_stop = True
            self.notify_event.set()
            ct.join()

class VirtualTimeBase(object):
    """Tests for virtual time functions when virtualtime is enabled"""
    def test_datetime_init(self):
        """tests the basic instantiation of datetime objects."""
        datetime.datetime(2012, 7, 25) # Richardg's birthday...hooray
        datetime.datetime(year=2012, month=7, day=25, hour=10, minute=27, second=3, microsecond=100, tzinfo=pytz.timezone('Africa/Johannesburg'))
        # test args, kwargs
        args = (2012,7,25)
        kwargs = {'hour':10, 'minute':27, 'second':3}
        kwargs_only = {'year':2012, 'month':7, 'day': 25, 'hour':10, 'minute':27, 'second':3, 'microsecond':100, 'tzinfo': pytz.timezone('Africa/Johannesburg')}
        datetime.datetime(*args)
        datetime.datetime(*args, **kwargs)
        datetime.datetime(**kwargs_only)

    def test_time(self):
        """tests that we can set time"""
        run_time_function_tst(time.time, virtualtime.set_time, 100, enabled=self.virtual_time_enabled)

    def test_localtime(self):
        """tests that we can set time and it affects localtime"""
        run_time_derived_function_tst(time.localtime, time.time, virtualtime.set_time, 100, min_diff=1, enabled=self.virtual_time_enabled)

    def test_gmtime(self):
        """tests that we can set time and it affects gmtime"""
        run_time_derived_function_tst(time.gmtime, time.time, virtualtime.set_time, 100, min_diff=1, enabled=self.virtual_time_enabled)

    def test_asctime(self):
        """tests that we can set time and it affects asctime"""
        order_preserving_asctime = lambda: order_preserving_timestr_reslice(time.asctime())
        run_time_derived_function_tst(order_preserving_asctime, time.time, virtualtime.set_time, 100, min_diff=1, enabled=self.virtual_time_enabled)

    def test_ctime(self):
        """tests that we can set time and it affects ctime"""
        order_preserving_ctime = lambda: order_preserving_timestr_reslice(time.ctime())
        run_time_derived_function_tst(order_preserving_ctime, time.time, virtualtime.set_time, 100, min_diff=1, enabled=self.virtual_time_enabled)

    def test_strftime(self):
        """tests that we can set time and it affects ctime"""
        strftime_iso = lambda: time.strftime("%Y-%m-%d %H:%M:%S")
        run_time_derived_function_tst(strftime_iso, time.time, virtualtime.set_time, 100, min_diff=1, enabled=self.virtual_time_enabled)

    def test_datetime_now(self):
        """tests that setting time and datetime are both possible"""
        run_time_function_tst(datetime.datetime.now, virtualtime.set_local_datetime, datetime.timedelta(seconds=100), enabled=self.virtual_time_enabled)

    def test_datetime_utcnow(self):
        """tests that setting time and datetime are both possible"""
        run_time_function_tst(datetime.datetime.utcnow, virtualtime.set_utc_datetime, datetime.timedelta(seconds=100), enabled=self.virtual_time_enabled)

    def test_datetime_tz_now(self):
        """tests that setting time and datetime are both possible"""
        run_time_function_tst(datetime_tz.datetime_tz.now, virtualtime.set_local_datetime, datetime.timedelta(seconds=100), enabled=self.virtual_time_enabled)

    def test_datetime_tz_utcnow(self):
        """tests that setting time and datetime are both possible"""
        run_time_function_tst(datetime_tz.datetime_tz.utcnow, virtualtime.set_utc_datetime, datetime.timedelta(seconds=100), enabled=self.virtual_time_enabled)

    def test_datetime_tz_now_other_tz(self):
        """tests that setting time and datetime are both possible"""
        for tz_name in ["Asia/Tokyo", "Europe/London", "America/Chicago"]:
            tz = pytz.timezone(tz_name)
            tz_now = lambda: datetime_tz.datetime_tz.now().astimezone(tz)
            run_time_derived_function_tst(tz_now, datetime_tz.datetime_tz.utcnow, virtualtime.set_utc_datetime, datetime.timedelta(seconds=100), enabled=self.virtual_time_enabled)

class TestDisabledVirtualTime(VirtualTimeBase, RunUnpatched):
    """Tests that virtual time functions have no effect when VirtualTime is disabled"""

class TestVirtualTime(VirtualTimeBase, RunPatched):
    """Tests that virtual time functions have no effect when VirtualTime is disabled"""

class SleepBase(object):
    def setup_method(self, method):  # This is a wrapper of setUp for py.test (py.test and nose take different method setup methods)
        self.setUp()

    def setUp(self):
        self.initial_waiter_count = len(virtualtime._virtual_time_state._Condition__waiters)

    def teardown_method(self, method):  # This is a wrapper of tearDown for py.test (py.test and nose take different method setup methods)
        self.tearDown()

    def tearDown(self):
        del self.initial_waiter_count

    def wait_sleep_started(self, sleep_count, max_wait=5.0):
        """Waits for the given number of sleeps to start before continuing (with a timeout)"""
        if not self.virtual_time_enabled:
            return
        start_wait_check = virtualtime._original_time()
        while len(virtualtime._virtual_time_state._Condition__waiters) < self.initial_waiter_count + sleep_count:
            virtualtime._original_sleep(0.001)
            delay = virtualtime._original_time() - start_wait_check
            if delay > max_wait:
                raise ValueError("Not enough sleepers started waiting in time...")

    @restore_time_after
    def test_sleep(self):
        """Tests that sleep comes back quicker than normal when time is advanced"""
        first_time = time.time()
        sleeper_thread = threading.Thread(target=time.sleep, args=(3,), name="test_sleep_sleeper")
        sleeper_thread.start()
        self.wait_sleep_started(1, 0.2)
        virtualtime.set_time(first_time + 5)
        sleeper_thread.join()
        virtualtime.restore_time()
        join_time = time.time()
        if self.virtual_time_enabled:
            assert join_time - first_time < 0.5
        else:
            assert join_time - first_time >= 3

    @restore_time_after
    def test_parallel_sleeps(self):
        """Tests that sleep comes back quicker than normal when time is advanced, and that this works with lots of threads"""
        first_time = virtualtime._original_time()
        sleeper_threads = {}
        REPEATS = 100
        for n in range(REPEATS):
            sleeper_threads[n] = sleeper_thread = threading.Thread(target=time.sleep, args=(3,), name="test_sleep_sleeper_%d" % n)
            sleeper_thread.start()
        self.wait_sleep_started(REPEATS, 0.5)
        thread_time = virtualtime._original_time()
        setup_duration = thread_time - first_time
        assert setup_duration < 0.5
        virtualtime.set_time(thread_time + 20)
        for n in range(REPEATS):
            sleeper_threads[n].join()
        join_time = virtualtime._original_time()
        sleep_duration = join_time - thread_time
        virtualtime.restore_time()
        if self.virtual_time_enabled:
            assert sleep_duration < 0.2
        else:
            assert sleep_duration >= 3

class TestDisabledSleep(SleepBase, RunUnpatched):
    pass

class TestSleep(SleepBase, RunPatched):
    @attr('long_running')
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
            offsets.append(virtualtime._time_offset)
            event.clear()

    @restore_time_after
    def test_fast_forward_time(self):
        """Test that fast forwarding the time works properly"""
        event = threading.Event()
        virtualtime.notify_on_change(event)
        offsets = []
        msg_dict = {'offsets': offsets}
        catcher_thread = threading.Thread(target=self.fast_forward_catcher, args=(event, msg_dict))
        catcher_thread.start()
        start_time = virtualtime._original_time()
        virtualtime.fast_forward_time(1)
        assert virtualtime._time_offset == 1
        virtualtime.fast_forward_time(2.5)
        assert virtualtime._time_offset == 3.5
        virtualtime.fast_forward_time(target=start_time + 9.1, step_size=2.0)
        assert 9 <= virtualtime._time_offset <= 9.2
        virtualtime.restore_time()
        virtualtime.fast_forward_time(-1.3, step_size=0.9)
        virtualtime.restore_time()
        msg_dict['stop'] = True
        event.set()
        catcher_thread.join()
        assert offsets[:6] == [1.0, 2.0, 3.0, 3.5, 5.5, 7.5]
        assert 9 <= offsets[6] <= 9.2
        assert offsets[7:11] == [0, -0.9, -1.3, 0]
        # depends on how long the stop event takes?
        assert (not offsets[11:]) or offsets[11:] == [0]

    @attr('long_running')
    @restore_time_after
    def test_fast_forward_time_long(self):
        """Test that fast forwarding the time a long way works properly"""
        event = threading.Event()
        virtualtime.notify_on_change(event)
        offsets = []
        msg_dict = {'offsets': offsets}
        catcher_thread = threading.Thread(target=self.fast_forward_catcher, args=(event, msg_dict))
        catcher_thread.start()
        start_time = virtualtime._original_time()
        virtualtime.fast_forward_time(1000, step_size=1)
        virtualtime.restore_time()
        msg_dict['stop'] = True
        event.set()
        catcher_thread.join()
        assert offsets == range(1, 1001) + [0]

    @restore_time_after
    def test_fast_forward_datetime_style(self):
        """Test that fast forwarding the time works properly when using datetime-style objects"""
        event = threading.Event()
        virtualtime.notify_on_change(event)
        offsets = []
        msg_dict = {'offsets': offsets}
        catcher_thread = threading.Thread(target=self.fast_forward_catcher, args=(event, msg_dict))
        catcher_thread.start()
        start_time = virtualtime._original_datetime_now()
        utc_start_time = datetime_tz.localize(start_time).astimezone(pytz.utc)
        virtualtime.fast_forward_timedelta(datetime.timedelta(seconds=1))
        assert virtualtime._time_offset == 1
        virtualtime.fast_forward_timedelta(datetime.timedelta(seconds=2.5))
        assert virtualtime._time_offset == 3.5
        virtualtime.fast_forward_local_datetime(target=start_time + datetime.timedelta(seconds=9.1), step_size=datetime.timedelta(seconds=2.0))
        assert 9 <= virtualtime._time_offset <= 9.2
        virtualtime.fast_forward_utc_datetime(target=utc_start_time + datetime.timedelta(seconds=18.2), step_size=datetime.timedelta(seconds=20.0))
        assert 18 <= virtualtime._time_offset <= 18.3
        virtualtime.restore_time()
        virtualtime.fast_forward_timedelta(datetime.timedelta(seconds=-1.3), step_size=datetime.timedelta(seconds=0.9))
        virtualtime.restore_time()
        msg_dict['stop'] = True
        event.set()
        catcher_thread.join()
        assert offsets[:6] == [1.0, 2.0, 3.0, 3.5, 5.5, 7.5]
        assert 9 <= offsets[6] <= 9.2
        assert 18 <= offsets[7] <= 18.3
        assert offsets[8:12] == [0, -0.9, -1.3, 0]
        # depends on how long the stop event takes?
        assert (not offsets[12:]) or offsets[12:] == [0]

    def fast_forward_delayer(self, notify_event, delay_event, msg_dict):
        offsets = msg_dict['offsets']
        positions = msg_dict['positions']
        while "stop" not in msg_dict:
            notify_event.wait()
            offsets.append(virtualtime._time_offset)
            position = positions.pop(0) if positions else ""
            if position == "start_job":
                virtualtime.delay_fast_forward_until_set(delay_event)
                virtualtime._original_sleep(0.1)
                delay_event.set()
            notify_event.clear()

    @restore_time_after
    def test_fast_forward_delay(self):
        """Test that fast forwarding the time works properly"""
        notify_event = threading.Event()
        virtualtime.notify_on_change(notify_event)
        delay_event = threading.Event()
        offsets = []
        positions = ["start_job", ""]
        msg_dict = {'offsets': offsets, 'positions': positions}
        catcher_thread = threading.Thread(target=self.fast_forward_delayer, args=(notify_event, delay_event, msg_dict))
        catcher_thread.start()
        start_time = virtualtime._original_time()
        virtualtime.fast_forward_time(2)
        assert virtualtime._time_offset == 2
        virtualtime.restore_time()
        msg_dict['stop'] = True
        notify_event.set()
        catcher_thread.join()
        completion_time = virtualtime._original_time()
        assert offsets[:3] == [1.0, 2.0, 0]
        # depends on how long the stop event takes?
        assert (not offsets[3:]) or offsets[3:] == [0]
        assert completion_time - start_time < 0.2
        assert delay_event.is_set()

class TestInheritance(object):
    """Tests how detection of inheritance works for datetime classes"""
    def setup_method(self, method):  # This is a wrapper of setUp for py.test (py.test and nose take different method setup methods)
        """Ensure that virtualtime is disabled when starting each test"""
        self.setUp()

    def setUp(self):
        while virtualtime.enabled():
            virtualtime.disable()

    def teardown_method(self, method):  # This is a wrapper of tearDown for py.test (py.test and nose take different method setup methods)
        self.tearDown()

    def tearDown(self):
        """Ensure that virtualtime is disabled after running each test"""
        while virtualtime.enabled():
            virtualtime.disable()

    def test_disabled(self):
        assert issubclass(datetime_tz.datetime_tz, datetime.datetime)

    def test_enabled(self):
        virtualtime.enable()
        assert issubclass(datetime_tz.datetime_tz, datetime.datetime)

    def test_switching(self):
        orig_datetime = datetime.datetime
        class derived_datetime(datetime.datetime):
            pass
        assert issubclass(datetime_tz.datetime_tz, orig_datetime)
        assert issubclass(datetime_tz.datetime_tz, datetime.datetime)
        assert issubclass(derived_datetime, orig_datetime)
        assert issubclass(derived_datetime, datetime.datetime)
        virtualtime.enable()
        class derived_datetime2(datetime.datetime):
            pass
        assert issubclass(datetime_tz.datetime_tz, orig_datetime)
        assert issubclass(datetime_tz.datetime_tz, datetime.datetime)
        assert issubclass(derived_datetime, orig_datetime)
        assert issubclass(derived_datetime, datetime.datetime)
        assert issubclass(derived_datetime2, orig_datetime)
        assert issubclass(derived_datetime2, datetime.datetime)
        virtualtime.disable()
        assert issubclass(datetime_tz.datetime_tz, orig_datetime)
        assert issubclass(datetime_tz.datetime_tz, datetime.datetime)
        assert issubclass(derived_datetime, orig_datetime)
        assert issubclass(derived_datetime, datetime.datetime)
        assert issubclass(derived_datetime2, orig_datetime)
        assert issubclass(derived_datetime2, datetime.datetime)

    def test_switching_values(self):
        now = datetime_tz.datetime_tz.now()
        assert isinstance(now, datetime.datetime)
        later = now + datetime.timedelta(hours=1)
        assert isinstance(later, datetime.datetime)
        start = datetime.datetime.combine(now.date(), now.time())
        assert isinstance(start, datetime.datetime)
        assert datetime_tz.localize(start) == now
        virtualtime.enable()
        now = datetime_tz.datetime_tz.now()
        assert isinstance(now, datetime.datetime)
        later = now + datetime.timedelta(hours=1)
        assert isinstance(later, datetime.datetime)
        start = datetime.datetime.combine(now.date(), now.time())
        assert isinstance(start, datetime.datetime)
        assert datetime_tz.localize(start) == now

_original_datetime_module = virtualtime._original_datetime_module
_original_datetime_type = virtualtime._original_datetime_type
_original_datetime_now = virtualtime._original_datetime_now
_original_datetime_utcnow = virtualtime._original_datetime_utcnow
_time_offset = virtualtime._time_offset

class virtual_datetime_tz_offset (virtualtime.virtual_datetime):

    @classmethod
    def now(cls, tz=None):
        """Virtualized datetime.datetime.now()"""
        return super(virtual_datetime_tz_offset, cls).now()

    @classmethod
    def utcnow(cls):
        """Virtualized datetime.datetime.utcnow()"""
        tz = getattr(datetime.datetime, "localtz_override") or datetime_tz.localtz()
        now = super(virtual_datetime_tz_offset, cls).now()
        #print now.replace(tzinfo=tz), tz.utcoffset(now.replace(tzinfo=tz))
        #print "utcnow", tz.localize(now).utcoffset()
        return now - tz.localize(now).utcoffset()


_original_vt_module = datetime.datetime

def patch_vt_module():
    """Patches the datetime module to work on virtual time"""
    datetime.datetime.now = virtual_datetime_tz_offset.now
    datetime.datetime.utcnow = virtual_datetime_tz_offset.utcnow

def unpatch_vt_module():
    """Restores the datetime module to work on real time"""
    datetime.datetime.now = _original_vt_module.now
    datetime.datetime.utcnow = _original_vt_module.utcnow

class TestVirtualDatetimeOffset:

    def setup(self):
        virtualtime.enable()
        datetime.datetime.localtz_override = pytz.timezone("America/Chicago")
        patch_vt_module()
        test_datetime_tz.patch_datetime_module()

    def teardown(self):
        virtualtime.disable()
        datetime.datetime.localtz_override = None
        unpatch_vt_module()
        test_datetime_tz.unpatch_datetime_module()




    def test_offset(self):
        """Make sure the offset is correct when using the localtz override"""
        localdatetime = datetime.datetime(2014,03,9,1,45,0)
        virtualtime.set_local_datetime(localdatetime)
        self.runTests(localdatetime)
        localdatetime = datetime.datetime(2014,03,9,2,45,0)
        virtualtime.set_local_datetime(localdatetime)
        self.runTests(localdatetime)
        localdatetime = datetime.datetime(2014,03,9,3,45,0)
        virtualtime.set_local_datetime(localdatetime)
        self.runTests(localdatetime)
        localdatetime = datetime.datetime(2014,11,2,0,45,0)
        virtualtime.set_local_datetime(localdatetime)
        self.runTests(localdatetime)
        localdatetime = datetime.datetime(2014,11,2,1,45,0)
        virtualtime.set_local_datetime(localdatetime)
        self.runTests(localdatetime)
        localdatetime = datetime.datetime(2014,11,2,2,45,0)
        virtualtime.set_local_datetime(localdatetime)
        self.runTests(localdatetime)
        #print datetime_tz.datetime_tz.now(), datetime.datetime.now()
        #print datetime_tz.datetime_tz.utcnow(), datetime.datetime.utcnow()

    def runTests(self,localdatetime):
        tz = datetime.datetime.localtz_override
        print "now"
        assert self.close_enough(datetime.datetime.now(), localdatetime)
        utcnow = datetime_tz.datetime_tz.utcnow()
        print "utcnow"
        assert self.close_enough(utcnow, tz.localize(localdatetime))
        now = datetime_tz.datetime_tz.now()
        print "_tznow"
        assert self.close_enough(now, tz.localize(localdatetime))

    def close_enough(self,dt,dt1):
        print dt,"\t", dt1
        return (dt - dt1) < datetime.timedelta(seconds=1)

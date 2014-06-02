#!/usr/bin/env python

"""Implements a system for simulating a virtual time (based on an offset from the current actual time) so that all Python objects believe it though the actual system time remains the same"""

import sys
import threading
import types
import time
import datetime as datetime_module
import weakref
if hasattr(weakref, 'WeakSet'):
    WeakSet = weakref.WeakSet
else:
    # python2.6 doesn't have WeakSet; we only use it to add and interate, so make a plan
    class WeakSet(weakref.WeakKeyDictionary):
        def add(self, item):
            self[item] = True

import logging

try:
    # pylint: disable-msg=C6204
    import functools
except ImportError as e:
    class functools(object):
      """Fake replacement for a full functools."""
      # pylint: disable-msg=W0613
      @staticmethod
      def wraps(f, *args, **kw):
          return f

TIME_CHANGE_LOG_LEVEL = logging.CRITICAL
MAX_CALLBACK_TIME = 1.0
MAX_DELAY_TIME = 60.0

_original_time = time.time
_original_asctime = time.asctime
_original_ctime = time.ctime
_original_gmtime = time.gmtime
_original_localtime = time.localtime
_original_strftime = time.strftime
_original_sleep = time.sleep

_virtual_time_state = threading.Condition()
# private variable that tracks whether virtual time is enabled - only to be used internally and locked with _virtual_time_state
__virtual_time_enabled = False
# In PyPy (as of 1.6) on all platforms, and CPython (as of 2.7.1) on Windows, datetime.datetime.[utc]now calls time.time()
_datetime_now_uses_time = ("PyPy" in sys.version or sys.platform == 'win32')
_virtual_time_notify_events = WeakSet()
_virtual_time_callback_events = WeakSet()
_fast_forward_delay_events = WeakSet()
_in_skip_time_change = False
_time_offset = 0

def notify_on_change(event):
    """adds the given event to a set that will be notified if the virtual time changes (does not need to be removed, as it's a weak ref)"""
    _virtual_time_state.acquire()
    try:
        _virtual_time_notify_events.add(event)
    finally:
        _virtual_time_state.release()

def undo_notify_on_change(event):
    """discards the given event from the set that will be notified if the virtual time changes (does not need to be removed, as it's a weak ref)"""
    _virtual_time_state.acquire()
    try:
        _virtual_time_notify_events.discard(event)
    finally:
        _virtual_time_state.release()

def wait_for_callback_on_change(event):
    """clear this event before notifying on change, and wait for it to be set before returning from the time change"""
    _virtual_time_state.acquire()
    try:
        _virtual_time_callback_events.add(event)
    finally:
        _virtual_time_state.release()

def undo_wait_for_callback_on_change(event):
    """discard this event from the callback set"""
    _virtual_time_state.acquire()
    try:
        _virtual_time_callback_events.discard(event)
    finally:
        _virtual_time_state.release()

def delay_fast_forward_until_set(event):
    """adds the given event to a set that will delay fast_forwards until they are set (does not need to be removed, as it's a weak ref)"""
    _virtual_time_state.acquire()
    try:
        _fast_forward_delay_events.add(event)
    finally:
        _virtual_time_state.release()

def undo_delay_fast_forward_until_set(event):
    """discards the given event from the set that will delay fast_forwards until they are set (does not need to be removed, as it's a weak ref)"""
    _virtual_time_state.acquire()
    try:
        _fast_forward_delay_events.discard(event)
    finally:
        _virtual_time_state.release()

def in_skip_time_change():
    """Indicates whether the offset change is a fast_forward or not"""
    _virtual_time_state.acquire()
    try:
        return _in_skip_time_change
    finally:
        _virtual_time_state.release()

def _virtual_time():
    """Overlayed form of time.time() that adds _time_offset"""
    return _original_time() + _time_offset

def _virtual_asctime(when_tuple=None):
    """Overlayed form of time.asctime() that adds _time_offset"""
    return _original_asctime(_virtual_localtime() if when_tuple is None else when_tuple)

def _virtual_ctime(when=None):
    """Overlayed form of time.ctime() that adds _time_offset"""
    return _original_ctime(_virtual_time() if when is None else when)

def _virtual_gmtime(when=None):
    """Overlayed form of time.gmtime() that adds _time_offset"""
    return _original_gmtime(_virtual_time() if when is None else when)

def _virtual_localtime(when=None):
    """Overlayed form of time.localtime() that adds _time_offset"""
    return _original_localtime(_virtual_time() if when is None else when)

def _virtual_strftime(format, when_tuple=None):
    """Overlayed form of time.strftime() that adds _time_offset"""
    return _original_strftime(format, _virtual_localtime() if when_tuple is None else when_tuple)

def _virtual_sleep(seconds):
    """Overlayed form of time.sleep() that responds to changes to the virtual time"""
    expected_end = _virtual_time() + seconds
    while True:
        remaining = expected_end - _virtual_time()
        if remaining <= 0:
            break
        # At least limit the fallout to a reasonably busy wait to get the lock
        if _virtual_time_state.acquire(False):
            try:
                remaining = expected_end - _virtual_time()
                _virtual_time_state.wait(remaining)
            finally:
                _virtual_time_state.release()
        else:
            _original_sleep(0.001)

_original_datetime_module = datetime_module
_underlying_datetime_type = _original_datetime_module.datetime

_virtual_datetime_attrs = dict(_underlying_datetime_type.__dict__.items())
class datetime(_original_datetime_module.datetime):
    def __new__(cls, *args, **kwargs):
        if args and isinstance(args[0], _underlying_datetime_type):
            dt = args[0]
        else:
            dt = _underlying_datetime_type.__new__(cls, *args, **kwargs)
        newargs = list(dt.timetuple()[0:6])+[dt.microsecond, dt.tzinfo]
        return _underlying_datetime_type.__new__(cls, *newargs)

    def astimezone(self, tzinfo):
        d = _underlying_datetime_type.astimezone(self, tzinfo)
        return _original_datetime_type.__new__(type(self), d)
    astimezone.__doc__ = _underlying_datetime_type.astimezone.__doc__

    def replace(self, **kw):
        d = _underlying_datetime_type.replace(self, **kw)
        return _original_datetime_type.__new__(type(self), d)
    replace.__doc__ = _underlying_datetime_type.replace.__doc__

    if _datetime_now_uses_time:
        @classmethod
        def now(cls, tz=None):
            """Virtualized datetime.datetime.now()"""
            # make the original datetime.now method counteract the offsets in time.time()
            dt = _underlying_datetime_type.now(tz=tz)
            if time.time != _original_time:
                dt = dt + _original_datetime_module.timedelta(seconds=-_time_offset)
            newargs = list(dt.timetuple()[0:6])+[dt.microsecond, dt.tzinfo]
            return _original_datetime_type.__new__(cls, *newargs)

        @classmethod
        def utcnow(cls):
            """Virtualized datetime.datetime.utcnow()"""
            # make the original datetime.utcnow method counteract the offsets in time.time()
            dt = _underlying_datetime_type.utcnow()
            if time.time != _original_time:
                dt = dt + _original_datetime_module.timedelta(seconds=-_time_offset)
            newargs = list(dt.timetuple()[0:6])+[dt.microsecond, dt.tzinfo]
            return _original_datetime_type.__new__(cls, *newargs)

    @classmethod
    def combine(cls, date, time):
        """date, time -> datetime with same date and time fields"""
        r = _underlying_datetime_type.combine(date, time)
        if isinstance(r, _underlying_datetime_type) and not isinstance(r, datetime_module.datetime):
            r = datetime_module.datetime(r)
        return r

    def __add__(self, other):
        r = _underlying_datetime_type.__add__(self, other)
        if isinstance(r, _underlying_datetime_type) and not isinstance(r, datetime_module.datetime):
            r = datetime_module.datetime(r)
        return r

    __radd__ = __add__

    def __sub__(self, other):
        r = _underlying_datetime_type.__sub__(self, other)
        if isinstance(r, _underlying_datetime_type) and not isinstance(r, datetime_module.datetime):
            r = datetime_module.datetime(r)
        return r

    def __rsub__(self, other):
        r = _underlying_datetime_type.__rsub__(self, other)
        if isinstance(r, _underlying_datetime_type) and not isinstance(r, datetime_module.datetime):
            r = datetime_module.datetime(r)
        return r

    if hasattr(_underlying_datetime_type, "__mul__"):
        def __mul__(self, other):
            r = _underlying_datetime_type.__mul__(self, other)
            if isinstance(r, _underlying_datetime_type) and not isinstance(r, datetime_module.datetime):
                r = datetime_module.datetime(r)
            return r

    if hasattr(_underlying_datetime_type, "__rmul__"):
        def __rmul__(self, other):
            r = _underlying_datetime_type.__rmul__(self, other)
            if isinstance(r, _underlying_datetime_type) and not isinstance(r, datetime_module.datetime):
                r = datetime_module.datetime(r)
            return r

    if hasattr(_underlying_datetime_type, "__div__"):
        def __div__(self, other):
            r = _underlying_datetime_type.__div__(self, other)
            if isinstance(r, _underlying_datetime_type) and not isinstance(r, datetime_module.datetime):
                r = datetime_module.datetime(r)
            return r

    if hasattr(_underlying_datetime_type, "__floordiv__"):
        def __floordiv__(self, other):
            r = _underlying_datetime_type.__floordiv__(self, other)
            if isinstance(r, _underlying_datetime_type) and not isinstance(r, datetime_module.datetime):
                r = datetime_module.datetime(r)
            return r

class virtual_datetime(datetime):
    @classmethod
    def now(cls, tz=None):
        """Virtualized datetime.datetime.now()"""
        dt = _original_datetime_now(tz=tz) + _original_datetime_module.timedelta(seconds=_time_offset)
        newargs = list(dt.timetuple()[0:6])+[dt.microsecond, dt.tzinfo]
        return _original_datetime_type.__new__(cls, *newargs)

    @classmethod
    def utcnow(cls):
        """Virtualized datetime.datetime.utcnow()"""
        dt = _original_datetime_utcnow() + _original_datetime_module.timedelta(seconds=_time_offset)
        newargs = list(dt.timetuple()[0:6])+[dt.microsecond, dt.tzinfo]
        return _original_datetime_type.__new__(cls, *newargs)

_original_datetime_type = datetime
_original_datetime_now = _original_datetime_type.now
_original_datetime_utcnow = _original_datetime_type.utcnow
_virtual_datetime_type = virtual_datetime
datetime_module.datetime = datetime
_virtual_datetime_now = _virtual_datetime_type.now
_virtual_datetime_utcnow = _virtual_datetime_type.utcnow

# NB: This helper function is a copy of j5.Basic.TimeUtils.totalseconds_float, but is here to prevent circular import - changes should be applied to both
def totalseconds_float(timedelta):
    """Return the total number of seconds represented by a datetime.timedelta object, including fractions of seconds"""
    return timedelta.seconds + (timedelta.days * 24 * 60 * 60) + timedelta.microseconds/1000000.0

def local_datetime_to_time(dt):
    """converts a naive datetime object to a local time float"""
    return time.mktime(dt.timetuple()) + dt.microsecond * 0.000001

def utc_datetime_to_time(dt):
    """converts a naive utc datetime object to a local time float"""
    return time.mktime(dt.utctimetuple()) + dt.microsecond * 0.000001 - (time.altzone if time.daylight else time.timezone)

def set_offset(new_offset, suppress_log=False, is_fast_forward_change=False):
    """Sets the current time offset to the given value"""
    global _time_offset
    global _in_skip_time_change
    try:
        _virtual_time_state.acquire()
        try:
            _in_skip_time_change = not is_fast_forward_change
            original_offset = _time_offset
            _time_offset = new_offset
            if not suppress_log:
                logging.log(TIME_CHANGE_LOG_LEVEL, "Virtual time offset adjusted from %r to %r at %r", original_offset, _time_offset, _original_datetime_now())
            callback_events = list(_virtual_time_callback_events)
            for event in callback_events:
                event.clear()
            _virtual_time_state.notify_all()
            for event in _virtual_time_notify_events:
                event.set()
        finally:
            _virtual_time_state.release()
        for event in callback_events:
            if not event.wait(MAX_CALLBACK_TIME):
                logging.warning("Virtual time callback was not received in %r seconds at %r", MAX_CALLBACK_TIME, _original_datetime_now())
    finally:
        _virtual_time_state.acquire()
        try:
            _in_skip_time_change = False
        finally:
            _virtual_time_state.release()

def get_offset():
    global _time_offset
    return _time_offset

def set_time(new_time, is_fast_forward_change=False):
    """Sets the current time to the given time.time()-equivalent value"""
    global _time_offset
    global _in_skip_time_change
    try:
        _virtual_time_state.acquire()
        try:
            _in_skip_time_change = not is_fast_forward_change
            original_offset = _time_offset
            _time_offset = new_time - _original_time()
            logging.log(TIME_CHANGE_LOG_LEVEL, "Virtual time offset adjusted from %r to %r at %r", original_offset, _time_offset, _original_datetime_now())
            callback_events = list(_virtual_time_callback_events)
            for event in callback_events:
                event.clear()
            _virtual_time_state.notify_all()
            for event in _virtual_time_notify_events:
                event.set()
        finally:
            _virtual_time_state.release()
        for event in callback_events:
            if not event.wait(MAX_CALLBACK_TIME):
                logging.warning("Virtual time callback was not received in %r seconds at %r", MAX_CALLBACK_TIME, _original_datetime_now())
    finally:
        _virtual_time_state.acquire()
        try:
            _in_skip_time_change = False
        finally:
            _virtual_time_state.release()

def restore_time():
    """Reverts to real time operation"""
    global _time_offset
    _virtual_time_state.acquire()
    try:
        original_offset = _time_offset
        _time_offset = 0
        logging.log(TIME_CHANGE_LOG_LEVEL, "Virtual time offset restored from %r to %r at %r", original_offset, _time_offset, _original_datetime_now())
        callback_events = list(_virtual_time_callback_events)
        for event in callback_events:
            event.clear()
        _virtual_time_state.notify_all()
        for event in _virtual_time_notify_events:
            event.set()
    finally:
        _virtual_time_state.release()
    for event in callback_events:
        if not event.wait(MAX_CALLBACK_TIME):
            logging.warning("Virtual time callback was not received in %r seconds at %r", MAX_CALLBACK_TIME, _original_datetime_now())

def set_local_datetime(dt):
    """Sets the current time using the given naive local datetime object"""
    set_time(local_datetime_to_time(dt))

def set_utc_datetime(dt):
    """Sets the current time using the given naive utc datetime object"""
    set_time(utc_datetime_to_time(dt))

def fast_forward_time(delta=None, target=None, step_size=1.0, step_wait=0.01, log_every=3600):
    """Moves through time to the target time or by the given delta amount, at the specified step pace, with small waits at each step. By default will log at delay events or every hour"""
    if (delta is None and target is None) or (delta is not None and target is not None):
        raise ValueError("Must specify exactly one of delta and target")
    _virtual_time_state.acquire()
    try:
        original_offset = _time_offset
        if target is not None:
            delta = target - original_offset - _original_time()
        logging.log(TIME_CHANGE_LOG_LEVEL, "Virtual time commencing fastforward from %r to %r at %r", original_offset, original_offset + delta, _original_datetime_now())
    finally:
        _virtual_time_state.release()
    _original_sleep(step_wait)
    if delta < 0:
        step_size = -step_size
    steps, part = divmod(delta, step_size)
    last_log = -1
    for step in range(1, int(steps)+1):
        _virtual_time_state.acquire()
        try:
            delay_events = list(_fast_forward_delay_events)
        finally:
            _virtual_time_state.release()
        message_logged = (last_log != step-1)
        for delay_event in delay_events:
            delay_time = MAX_DELAY_TIME
            if not message_logged and delay_time >= step_wait:
                # try a minimal wait, and log if a larger delay is happening
                if delay_event.wait(step_wait):
                    continue
                else:
                    logging.log(TIME_CHANGE_LOG_LEVEL, "Virtual time fastforward offset at %r waiting for delay_event at %r", _time_offset, _original_datetime_now())
                    message_logged, last_log = True, step
                    delay_time -= step_wait
            if not delay_event.wait(delay_time):
                logging.warning("A delay_event %r was not set despite waiting %0.2f seconds - continuing to travel through time...", delay_event, MAX_DELAY_TIME)
        set_offset(original_offset + step*step_size, suppress_log=True, is_fast_forward_change=True)
        if log_every and step - last_log == log_every:
            logging.log(TIME_CHANGE_LOG_LEVEL, "Virtual time fastforward offset at %r at %r", _time_offset, _original_datetime_now())
            last_log = step
        _original_sleep(step_wait)
    if part != 0:
        _virtual_time_state.acquire()
        try:
            delay_events = list(_fast_forward_delay_events)
        finally:
            _virtual_time_state.release()
        for delay_event in delay_events:
            if not delay_event.wait(MAX_DELAY_TIME):
                logging.warning("A delay_event %r was not set despite waiting %0.2f seconds - continuing to travel through time...", delay_event, MAX_DELAY_TIME)
        set_offset(original_offset + delta, suppress_log=True, is_fast_forward_change=True)
        _original_sleep(step_wait)
    logging.log(TIME_CHANGE_LOG_LEVEL, "Virtual time completed fastforward from %r to %r at %r", original_offset, _time_offset, _original_datetime_now())

def fast_forward_timedelta(delta, step_size=1.0, step_wait=0.01):
    """Moves through time by the given datetime.timedelta amount, at the specified step pace, with small waits at each step"""
    if isinstance(step_size, _original_datetime_module.timedelta):
        step_size = totalseconds_float(step_size)
    if isinstance(step_wait, _original_datetime_module.timedelta):
        step_wait = totalseconds_float(step_wait)
    delta = totalseconds_float(delta)
    fast_forward_time(delta=delta, step_size=step_size, step_wait=step_wait)

def fast_forward_local_datetime(target, step_size=1.0, step_wait=0.01):
    """Moves through time to the target time, at the specified step pace, with small waits at each step"""
    if isinstance(step_size, _original_datetime_module.timedelta):
        step_size = totalseconds_float(step_size)
    if isinstance(step_wait, _original_datetime_module.timedelta):
        step_wait = totalseconds_float(step_wait)
    target = local_datetime_to_time(target)
    fast_forward_time(target=target, step_size=step_size, step_wait=step_wait)

def fast_forward_utc_datetime(target, step_size=1.0, step_wait=0.01):
    """Moves through time to the target time, at the specified step pace, with small waits at each step"""
    if isinstance(step_size, _original_datetime_module.timedelta):
        step_size = totalseconds_float(step_size)
    if isinstance(step_wait, _original_datetime_module.timedelta):
        step_wait = totalseconds_float(step_wait)
    target = utc_datetime_to_time(target)
    fast_forward_time(target=target, step_size=step_size, step_wait=step_wait)

# Functions to patch and unpatch date/time modules

def patch_time_module():
    """Patches the time module to work on virtual time"""
    time.time = _virtual_time
    time.asctime = _virtual_asctime
    time.ctime = _virtual_ctime
    time.gmtime = _virtual_gmtime
    time.localtime = _virtual_localtime
    time.strftime = _virtual_strftime
    time.sleep = _virtual_sleep

def unpatch_time_module():
    """Restores the time module to use original functions"""
    time.time = _original_time
    time.asctime = _original_asctime
    time.ctime = _original_ctime
    time.gmtime = _original_gmtime
    time.localtime = _original_localtime
    time.strftime = _original_strftime
    time.sleep = _original_sleep

def patch_datetime_module():
    """Patches the datetime module to work on virtual time"""
    _original_datetime_module.datetime.now = _virtual_datetime_now
    _original_datetime_module.datetime.utcnow = _virtual_datetime_utcnow

def unpatch_datetime_module():
    """Restores the datetime module to work on real time"""
    _original_datetime_module.datetime.now = _original_datetime_now
    _original_datetime_module.datetime.utcnow = _original_datetime_utcnow

raw_time = _original_time
raw_datetime = _underlying_datetime_type

def is_datetime_instance(value):
    """
    It is possible for there to be some datetime instances in the system that are subclasses of the
    unpatched datetime class - either created before it was patched, or created in C code in some
    tricksy way (for example, some dates coming from databases end up like this)
    """
    return isinstance(value, raw_datetime)

def enabled():
    """Checks whether virtual time has been enabled by examing modules - returns a ValueError if in an inconsistent state"""
    check_functions = [
        ("time.time",         time.time,      _original_time,      _virtual_time),
        ("time.asctime",      time.asctime,   _original_asctime,   _virtual_asctime),
        ("time.ctime",        time.ctime,     _original_ctime,     _virtual_ctime),
        ("time.gmtime",       time.gmtime,    _original_gmtime,    _virtual_gmtime),
        ("time.localtime",    time.localtime, _original_localtime, _virtual_localtime),
        ("time.strftime",     time.strftime,  _original_strftime,  _virtual_strftime),
        ("time.sleep",        time.sleep,     _original_sleep,     _virtual_sleep),
        ("datetime.datetime.now",    _original_datetime_module.datetime.now,    _original_datetime_now,    _virtual_datetime_now),
        ("datetime.datetime.utcnow", _original_datetime_module.datetime.utcnow, _original_datetime_utcnow, _virtual_datetime_utcnow),
    ]
    constant_functions = [
        ("datetime.datetime", _original_datetime_module.datetime, _original_datetime_type),
        ("threading._time",   threading._time,                    _original_time),
        ("threading._sleep",  threading._sleep,                   _original_sleep),
    ]
    for check_name, check_function, correct_function in constant_functions:
        if check_function != correct_function:
            raise ValueError("%s should be %s but has been patched as %s" % (check_name, check_function, correct_function))
    check_results = {}
    for check_name, check_function, orig_function, virtual_function in check_functions:
        check_results[check_name] = "orig" if check_function == orig_function else ("virtual" if check_function == virtual_function else "unexpected")
    combined_results = set(check_results.values())
    if "unexpected" in combined_results:
        logging.critical("Unexpected functions in virtual time patching: %s", ", ".join(check_name for check_name, check_status in check_results.items() if check_status == 'unexpected'))
    if len(combined_results) > 1:
        logging.critical("Inconsistent state of virtual time patching: %r", check_results)
        raise ValueError("Inconsistent state of virtual time patching")
    state = list(combined_results)[0]
    if state == "unexpected":
        raise ValueError("Unexpected functions in virtual time patching")
    return state == 'virtual'

def enable():
    """Enables virtual time (actually increments the number of times it's been enabled)"""
    global __virtual_time_enabled
    _virtual_time_state.acquire()
    try:
        __virtual_time_enabled = True
        logging.info("Virtual Time enabled %d times; patching modules", __virtual_time_enabled)
        patch_time_module()
        patch_datetime_module()
    finally:
        _virtual_time_state.release()

def disable():
    """Disables virtual time (actually decrements the number of times it's been enabled, and disables if 0)"""
    global __virtual_time_enabled
    _virtual_time_state.acquire()
    try:
        __virtual_time_enabled = False
        logging.info("Virtual Time disabled %d times; unpatching modules", __virtual_time_enabled)
        unpatch_time_module()
        unpatch_datetime_module()
    finally:
        _virtual_time_state.release()

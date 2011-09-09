#!/usr/bin/env python

"""Implements a system for simulating a virtual time (based on an offset from the current actual time) so that all Python objects believe it though the actual system time remains the same"""

# TODO: see to what extent it is possible to only patch the functions when a virtual time is in place...

import sys
import threading
import types
import time
import datetime as datetime_module
import weakref

_original_time = time.time
_original_asctime = time.asctime
_original_ctime = time.ctime
_original_gmtime = time.gmtime
_original_localtime = time.localtime
_original_strftime = time.strftime
_original_sleep = time.sleep

_virtual_time_state = threading.Condition()
_virtual_time_notify_events = weakref.WeakSet()
_time_offset = 0

def notify_on_change(event):
    """adds the given event to a list that will be notified if the virtual time changes (does not need to be removed, as it's a weak ref)"""
    _virtual_time_notify_events.add(event)

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

time.time = _virtual_time
time.asctime = _virtual_asctime
time.ctime = _virtual_ctime
time.gmtime = _virtual_gmtime
time.localtime = _virtual_localtime
time.strftime = _virtual_strftime
time.sleep = _virtual_sleep

_original_datetime_module = datetime_module
_original_datetime_type = _original_datetime_module.datetime
_original_datetime_now = _original_datetime_type.now
_original_datetime_utcnow = _original_datetime_type.utcnow

_virtual_datetime_attrs = dict(_original_datetime_type.__dict__.items())
class datetime(_original_datetime_module.datetime):
    def __new__(cls, *args, **kwargs):
        dt = super(_virtual_datetime_type, cls).__new__(cls, *args, **kwargs)
        newargs = list(dt.timetuple()[0:6])+[dt.microsecond, dt.tzinfo]
        return _original_datetime_type.__new__(cls, *newargs)

    @classmethod
    def now(cls):
        """Virtualized datetime.datetime.now()"""
        dt = super(_virtual_datetime_type, cls).now() + _original_datetime_module.timedelta(seconds=_time_offset)
        newargs = list(dt.timetuple()[0:6])+[dt.microsecond, dt.tzinfo]
        return _original_datetime_type.__new__(cls, *newargs)

    @classmethod
    def utcnow(cls):
        """Virtualized datetime.datetime.utcnow()"""
        dt = super(_virtual_datetime_type, cls).utcnow() + _original_datetime_module.timedelta(seconds=_time_offset)
        newargs = list(dt.timetuple()[0:6])+[dt.microsecond, dt.tzinfo]
        return _original_datetime_type.__new__(cls, *newargs)

_virtual_datetime_type = datetime
_original_datetime_module.datetime = _virtual_datetime_type

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

def set_offset(new_offset):
    """Sets the current time offset to the given value"""
    global _time_offset
    _virtual_time_state.acquire()
    try:
        _time_offset = new_offset
        _virtual_time_state.notify_all()
        for event in _virtual_time_notify_events:
            event.set()
    finally:
        _virtual_time_state.release()

def fast_forward_time(delta=None, target=None, step_size=1.0, step_wait=0.01):
    """Moves through time to the target time or by the given delta amount, at the specified step pace, with small waits at each step"""
    if (delta is None and target is None) or (delta is not None and target is not None):
        raise ValueError("Must specify exactly one of delta and target")
    _virtual_time_state.acquire()
    try:
        original_offset = _time_offset
        if target is not None:
            delta = target - original_offset - _original_time()
    finally:
        _virtual_time_state.release()
    _original_sleep(step_wait)
    if delta < 0:
        step_size = -step_size
    steps, part = divmod(delta, step_size)
    # TODO: adjust this so that if scheduled tasks run, it waits for them to complete before charging forth
    for step in range(1, int(steps)+1):
        set_offset(original_offset + step*step_size)
        _original_sleep(step_wait)
    if part != 0:
        set_offset(original_offset + delta)
        _original_sleep(step_wait)

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

def set_time(new_time):
    """Sets the current time to the given time.time()-equivalent value"""
    global _time_offset
    _virtual_time_state.acquire()
    try:
        _time_offset = new_time - _original_time()
        _virtual_time_state.notify_all()
        for event in _virtual_time_notify_events:
            event.set()
    finally:
        _virtual_time_state.release()

def restore_time():
    """Reverts to real time operation"""
    global _time_offset
    _virtual_time_state.acquire()
    try:
        _time_offset = 0
        _virtual_time_state.notify_all()
        for event in _virtual_time_notify_events:
            event.set()
    finally:
        _virtual_time_state.release()

def set_local_datetime(dt):
    """Sets the current time using the given naive local datetime object"""
    set_time(local_datetime_to_time(dt))

def set_utc_datetime(dt):
    """Sets the current time using the given naive utc datetime object"""
    set_time(utc_datetime_to_time(dt))


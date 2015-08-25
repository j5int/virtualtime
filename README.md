virtualtime
===========

Implements a system for simulating a virtual time (based on an offset from the current actual time)
so that all Python objects believe it though the actual system time remains the same.

This also includes an extension to the python-datetime-tz library (`datetime_tz`) that ensures that the
classes are all patched in the correct order. It also changes the behaviour of `datetime_tz.datetime_tz` objects
to allow them to be compared with naive `datetime.datetime` objects by assuming that they are in the local timezone, if unspecified.

This always patches `time.strftime` and `datetime.datetime.strftime` to support pre-1900 and pre-1000 years
and to not map years between `0` and `99` to the years `1969` to `2068`, on versions prior to Python 3.3
(where all years are supported without any strange mapping), even when `virtualtime` is not enabled.
See http://bugs.python.org/issue1777412 for a discussion on the Python 2.7 behaviour

This library is licensed under the Apache License, Version 2.0, and is published on pypi at
https://pypi.python.org/pypi/virtualtime

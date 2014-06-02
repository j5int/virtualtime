virtualtime
===========

Implements a system for simulating a virtual time (based on an offset from the current actual time)
so that all Python objects believe it though the actual system time remains the same.

This also includes an extension to the python-datetime-tz library (datetime_tz) that ensures that the
classes are all patched in the correct order. It also changes the behaviour of datetime_tz.datetime_tz objects
to allow them to be compared with naive datetime.datetime objects by assuming that they are in the local timezone, if unspecified.

This library is licensed under the Apache License, Version 2.0.
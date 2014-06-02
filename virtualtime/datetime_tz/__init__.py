__author__ = 'matth'

#We need to import this first, so that it patches datetime.datetime before datetime_tz extends it
import virtualtime
patched_datetime_type = virtualtime._original_datetime_type
import datetime_tz as base_datetime_tz
assert issubclass(base_datetime_tz.datetime_tz, patched_datetime_type), 'The base datetime_tz package must not be imported before virtualtime'

from datetime_tz import detect_timezone, iterate, localtz
from datetime_tz import localtz_set, timedelta, localize, get_naive, localtz_name, require_timezone

class datetime_tz(base_datetime_tz.datetime_tz):

  def __eq__(self, other):
    if isinstance(other, patched_datetime_type) and other.tzinfo is None:
        other = localize(other)
    return super(datetime_tz, self).__eq__(other)

  def __gt__(self, other):
    if isinstance(other, patched_datetime_type) and other.tzinfo is None:
        other = localize(other)
    return super(datetime_tz, self).__gt__(other)

  def __ge__(self, other):
    if isinstance(other, patched_datetime_type) and other.tzinfo is None:
        other = localize(other)
    return super(datetime_tz, self).__ge__(other)

  def __lt__(self, other):
    if isinstance(other, patched_datetime_type) and other.tzinfo is None:
        other = localize(other)
    return super(datetime_tz, self).__lt__(other)

  def __le__(self, other):
    if isinstance(other, patched_datetime_type) and other.tzinfo is None:
        other = localize(other)
    return super(datetime_tz, self).__le__(other)

  def __ne__(self, other):
    if isinstance(other, patched_datetime_type) and other.tzinfo is None:
        other = localize(other)
    return super(datetime_tz, self).__ne__(other)

__all__ = ['datetime_tz', 'base_datetime_tz', 'detect_timezone', 'iterate', 'localtz',
    'localtz_set', 'localtz_name', 'timedelta', 'get_naive', 'require_timezone', 'localize']
#! /usr/bin/env python
# Unit tests for Indigo Omni Link plugin
#
# Copyright (C) 2016 Gemini Lasswell
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
""" Miscellaneous test fixtures for Omni Link plugin unit tests """
from datetime import datetime, timedelta

import pytest


class TestException(Exception):
    pass


def run_concurrent_thread(plugin, time_limit):
    """ call run_concurrent_thread, with sleep patched so it doesn't delay """
    plugin.StopThread = TestException

    class local:
        now = 0

    def sleep(seconds):
        if local.now > time_limit:
            raise TestException("done")
        local.now += seconds

    plugin.sleep = sleep
    plugin.runConcurrentThread()


class PatchableDatetime(datetime):
    """ A replacement for datetime that replaces datetime.now() """
    not_the_actual_time = datetime(2011, 10, 9, 8, 7, 6)

    def __new__(cls, *args, **kwargs):
        return datetime.__new__(datetime, *args, **kwargs)

    @classmethod
    def set_now_for_test(cls, dt):
        cls.not_the_actual_time = dt

    @classmethod
    def fast_forward(cls, *args, **kwargs):
        td = timedelta(*args, **kwargs)
        cls.not_the_actual_time += td

    @classmethod
    def now(cls):
        return cls.not_the_actual_time


@pytest.fixture
def patched_datetime(monkeypatch):
    """ Patch datetime.datetime with a fake datetime class with these methods:
    patched_datetime.set_now_for_test(dt) - set a the next return value for now
    fast_forward(timedelta) - move now ahead by timedelta
    """
    monkeypatch.setattr("datetime.datetime", PatchableDatetime)
    return PatchableDatetime

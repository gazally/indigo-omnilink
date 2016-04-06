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

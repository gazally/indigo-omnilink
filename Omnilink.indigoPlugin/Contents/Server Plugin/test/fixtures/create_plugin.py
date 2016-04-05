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
from __future__ import print_function
from __future__ import unicode_literals
from StringIO import StringIO
from subprocess import Popen
import time

import mock
from mock import Mock
import pytest


@pytest.fixture(scope="session")
def version():
    """Return the version number. Which we should really get from
    info.plist.
    """
    return "0.2.0"


@pytest.fixture(autouse=True)
def popen(monkeypatch):
    """ Monkey patch Popen so it doesn't launch java, but does have
    a stdout that a line of text can be read from """
    javaproc_mock = Mock()
    javaproc_mock.stdout = StringIO("Java Gateway started\n")
    javaproc_mock.stderr = StringIO("")
    popen_mock = mock.create_autospec(Popen)
    popen_mock.return_value = javaproc_mock
    monkeypatch.setattr("subprocess.Popen", popen_mock)
    return popen_mock


@pytest.fixture
def gateway(py4j):
    """ Mock the return value from py4j.java_gateway.JavaGateway """
    gateway = Mock()
    py4j.java_gateway.JavaGateway.return_value = gateway
    return gateway


@pytest.yield_fixture
def plugin(version, plugin_module, monkeypatch, jomnilinkII):
    """ Create a new plugin object and start it. On teardown,
    shut it down and assert that it didn't log any errors.
    """
    props = {"showDebugInfo": False,
             "showJomnilinkIIDebugInfo": False}
    plugin = plugin_module.Plugin("", "", version, props)

    # Patch time.sleep to short circuit the plugin's wait for
    # its java subprocess to start. The java subprocess has been mocked,
    # but the plugin still starts a thread to read from the mock's stdout.
    #
    sleep = time.sleep
    mocksleep = Mock(side_effect=lambda t: sleep(t/100))
    monkeypatch.setattr("time.sleep", mocksleep)
    plugin.startup()
    yield plugin

    plugin.shutdown()
    # if you are testing error code, use reset_mock()
    assert not plugin.errorLog.called

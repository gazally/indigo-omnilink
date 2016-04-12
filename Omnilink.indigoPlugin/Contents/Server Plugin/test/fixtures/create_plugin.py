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


@pytest.fixture
def security_find_func(enckey1, enckey2):
    """return the mock that will be called by the communicate method of
    the return value of the monkeypatched Popen when given the
    security find-internet-password command
    """
    return Mock(
        return_value=("", 'password: "{0}"\n'.format("-".join([enckey1,
                                                               enckey2]))))


@pytest.fixture
def security_add_func(enckey1, enckey2):
    """return the mock that will be called by the communicate method of
    the return value of the monkeypatched Popen when given the
    security add-internet-password command
    """
    return Mock(return_value=("", ""))


@pytest.fixture(autouse=True)
def popen(monkeypatch, security_find_func, security_add_func):
    """ Monkey patch Popen so it returns a mock with appropriate behavior """

    def security_imposter(command):
        if command.startswith("find-internet-password"):
            return security_find_func()
        elif command.startswith("add-internet-password"):
            return security_add_func()

    def popen_imposter(command, stdin=None, stdout=None, stderr=None):
        """ Return a Mock to stand in for the return value from
        subprocess.Popen """
        if "java" in command[0]:
            # Need a stdout that a line of text can be read from
            javaproc_mock = Mock()
            javaproc_mock.stdout = StringIO("Java Gateway started\n")
            javaproc_mock.stderr = StringIO("")
            return javaproc_mock
        elif "security" in command[0]:
            m = Mock()
            m.communicate.side_effect = security_imposter
            return m
        else:
            assert False

    popen_mock = Mock(side_effect=popen_imposter)
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

#! /usr/bin/env python
# Unit Tests for Omnilink Plugin for Indigo Server
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

import datetime
from functools import partial
import logging
import mock
from mock import patch, Mock, MagicMock
import os
import StringIO
import subprocess
import sys
from threading import Thread
import time
import unittest
from unittest import TestCase

import indigo_mock

_VERSION = "0.1.0"

plugin_path = os.path.abspath(
    '../Omnilink.indigoPlugin/Contents/Server Plugin')

# There are two modules used in the plugin, indigo and
# py4j, which should not be in the test environment because they have too
# many real world side effects, so do some mocking first.

if plugin_path not in sys.path:
    sys.path.append(plugin_path)

if 'plugin' not in sys.modules:
    sys.modules['indigo'] = indigo_mock.mock_indigo
    sys.modules['py4j'] = MagicMock()
    sys.modules['py4j.java_gateway'] = sys.modules['py4j'].java_gateway
    sys.modules['py4j.protocol'] = sys.modules['py4j'].protocol

concurrent_thread_time = 0.1


class TestException(Exception):
    pass


class Py4JError(Exception):
    pass


class Fixture(object):
    """ A simple scheme for test fixtures. Fixtures need to implement
    two methods:
    setUp -- create test setup and put it in attributes of testcase
    tearDown -- do whatever cleanup is necessary
    """
    def setUp(self, testcase):
        pass

    def tearDown(self):
        pass


def CompositeFixture(*fixture_classes):
    """ so you can do this:
    BiggerFixture = CompositeFixture(LittleFixture, OtherLittleFixture)
    A newly created BiggerFixture instance will create instances
    of the fixture classes passed to CompositeFixture. Its setUp method
    will call their setUp methods in order and its tearDown method
    will call their tearDown methods in reverse order.
    """
    class ConstructedFixture(Fixture):
        def __init__(self):
            self._fixtures = [cls() for cls in fixture_classes]

        def setUp(self, testcase):
            [fixture.setUp(testcase) for fixture in self._fixtures]

        def tearDown(self):
            [fixture.tearDown() for fixture in reversed(self._fixtures)]

    ConstructedFixture.__name__ = str("".join((cls.__name__
                                               for cls in fixture_classes)))
    return ConstructedFixture


class TestCaseWithFixtures(TestCase):
    """ Subclass of unittest.TestCase that provides accounting of fixtures.
    Subclasses should call:
    setUp -- do whatever you want, but you need to call
             TestCaseWithFixtures.setUp before using any fixtures
    useFixture -- will create a fixture instance, run its setUp (which
        will build test objects and assign them to the TestCase's
        self.whatever) and add the fixture instance to the list of things
        that need to be torn down
    tearDown -- if a child class implements tearDown,
             TestCaseWithFixtures.tearDown must be called to do cleanup
    """
    def setUp(self):
        self._fixtures = []

    def useFixture(self, cls):
        fixture = cls()
        fixture.setUp(self)
        self._fixtures.append(fixture)
        return fixture

    def tearDown(self):
        [fixture.tearDown() for fixture in reversed(self._fixtures)]

# ----- Shared Test Fixtures ----- #


class POpenPatchFixture(Fixture):
    """ No Fixture Dependencies.
    Create a mock to be the return value from the java subprocess.
    """
    def setUp(self, tc):
        """ make a Mock to pretend to be the java subprocess """
        tc.javaproc_mock = mock.create_autospec(subprocess.Popen)
        tc.javaproc_mock.stdout = StringIO.StringIO("stdout\n")
        tc.javaproc_mock.stderr = StringIO.StringIO("")
        self.popen_patcher = patch("plugin.subprocess.Popen",
                                   Mock(return_value=tc.javaproc_mock))
        self.popen_patcher.start()

    def tearDown(self):
        self.popen_patcher.stop()


class JavaGatewayFixture(Fixture):
    """ No Fixture dependencies.
    Create a mock to be the return value of py4j.JavaGateway
    """
    def setUp(self, tc):
        tc.gateway_mock = Mock()
        tc.py4j_mock = sys.modules['py4j']
        tc.py4j_mock.java_gateway.JavaGateway.return_value = tc.gateway_mock
        tc.py4j_mock.protocol.Py4JError = Py4JError
        tc.jomnilinkII_mock = tc.gateway_mock.jvm.com.digitaldan.jomnilinkII


class MockConnectionFixture(Fixture):
    """ Depends on JavaGatewayFixture.
    Creates a mock of the jomnilinkII Connection object.
    """
    def setUp(self, tc):
        # Mock up connection objects -- allow for multiple connections
        tc.connection_mocks = [Mock(), Mock()]
        tc.connection_mock = tc.connection_mocks[0]
        tc.jomnilinkII_mock.Connection.side_effect = tc.connection_mocks

        # build our own callback functionality so notification and
        # disconnect listeners can be tested
        # keep separate lists for each mock connection object
        self.notify_listeners = tc.notify_listeners = []
        self.disconnect_listeners = tc.disconnect_listeners = []

        for i in range(len(tc.connection_mocks)):
            cm = tc.connection_mocks[i]
            cm.addNotificationListener.side_effect = partial(self.add_notify,
                                                             i)
            tc.notify_listeners.append([])
            cm.addDisconnectListener.side_effect = partial(self.add_disconnect,
                                                           i)
            tc.disconnect_listeners.append([])

    def add_notify(self, i, notify_listener):
        self.notify_listeners[i].append(notify_listener)

    def add_disconnect(self, i, disconnect_listener):
        self.disconnect_listeners[i].append(disconnect_listener)


class IndigoModuleFixture(Fixture):
    def setUp(self, tc):
        # reset any global state in our indigo mockup
        indigo_mock.reset()

        # run tests from test directory, or this will fail
        import plugin

        # indigo starts the plugin with current directory set to Server Plugin
        # so do the same here
        tc.plugin_module = plugin
        os.chdir(plugin_path)
        self.tc = tc

    def tearDown(self):
        # use reset_mock if you are testing an error condition
        self.tc.assertFalse(
            self.tc.plugin_module.indigo.PluginBase.errorLog.called)

PluginEnvironmentFixture = CompositeFixture(POpenPatchFixture,
                                            JavaGatewayFixture,
                                            MockConnectionFixture,
                                            IndigoModuleFixture)


class NewPluginFixture(Fixture):
    def setUp(self, tc):
        """ create and start a plugin object """
        props = {}
        props["showDebugInfo"] = False
        props["showJomnilinkIIDebugInfo"] = False

        self.plugin = tc.plugin = tc.plugin_module.Plugin("", "", _VERSION,
                                                          props)

        # patch time.sleep to short circuit the plugin's wait for
        # its java subprocess to start
        sleep = time.sleep
        with patch('plugin.time.sleep') as ts:
            ts.side_effect = lambda t: sleep(t/100)
            tc.plugin.startup()

    def tearDown(self):
        self.plugin.shutdown()

    @staticmethod
    def run_concurrent_thread(tc, plugin, time_limit):
        plugin.StopThread = TestException

        class local:
            now = 0

        def sleep(seconds):
            if local.now > time_limit:
                raise TestException("done")
            local.now += seconds

        plugin.sleep = sleep
        t = Thread(target=plugin.runConcurrentThread)
        t.setDaemon(True)
        t.start()
        time.sleep(0.1)
        tc.assertFalse(t.is_alive())

PluginStartedFixture = CompositeFixture(PluginEnvironmentFixture,
                                        NewPluginFixture)


class ConnectionValuesFixture(Fixture):
    # this should match the inital state in Device_Factory.xml
    device_factory_dialog_flags = {"isConnected": False,
                                   "error": False,
                                   "connectionError": False,
                                   "ipAddressError": False,
                                   "portNumberError": False,
                                   "encryptionKey1Error": False,
                                   "encryptionKey2Error": False}

    def setUp(self, tc):
        tc.values = {"ipAddress": "192.168.1.42",
                     "portNumber": "4444",
                     "encryptionKey1": "01-23-45-67-89-AB-CD-EF",
                     "encryptionKey2": "01-23-45-67-89-AB-CD-EF",
                     "prefix": ""}
        tc.values.update(self.device_factory_dialog_flags)
        tc.values2 = {"ipAddress": "10.0.0.2",
                      "portNumber": "4444",
                      "encryptionKey1": "01-23-45-67-89-AB-CD-EF",
                      "encryptionKey2": "01-23-45-67-89-AB-CD-EF",
                      "prefix": ""}
        tc.values2.update(self.device_factory_dialog_flags)


def build_java_class_mimic(argnames):
    """ jomnilinkII contains many boilerplate classes that just have a
lot of getWhatever() methods. Build mimics of them, given the list of
Whatevers they contain.

JomnilinkII_status_msg_for_test = build_java_class_mimic(
    ["StatusType", "Statuses"])

produces this:

class JomnilinkII_status_msg_for_test(object):
    def __init__(self, StatusType, Statuses):
        self.StatusType, self.Statuses = StatusType, Statuses
    def getStatusType(self):
        return self.StatusType
    def getStatuses(self):
        return self.Statuses

Isn't Python wonderful?
    """
    class Result(object):
        def __init__(self, *args):
            for name, arg in zip(argnames, args):
                setattr(self, name, arg)

        def toString(self):
            return " ".join(argnames)

    def make_method(argname):
        def method(self):
            return getattr(self, argname)
        return method

    for name in argnames:
        setattr(Result, "get" + name, make_method(name))
    return Result

JomnilinkII_ObjectStatus_for_test = build_java_class_mimic(
    ["StatusType", "Statuses"])

JomnilinkII_ZoneProperties_for_test = build_java_class_mimic(
    ["MessageType", "Name", "Number", "ZoneType", "Area", "Options"])

JomnilinkII_ObjectProperties_for_test = build_java_class_mimic(
    ["ObjectType", "Number", "Name", "MessageType"])

JomnilinkII_SystemInformation_for_test = build_java_class_mimic(
    ["Model", "Major", "Minor", "Revision", "Phone"])

JomnilinkII_ZoneStatus_for_test = build_java_class_mimic(
    ["Number", "Status", "Loop"])

JomnilinkII_SystemTroubles_for_test = build_java_class_mimic(
    ["Troubles"])

JomnilinkII_SystemStatus_for_test = build_java_class_mimic(
    ["BatteryReading"])

JomnilinkII_SecurityCodeValidation_for_test = build_java_class_mimic(
    ["CodeNumber", "AuthorityLevel"])

JomnilinkII_OtherEventNotifications_for_test = build_java_class_mimic(
    ["Notifications"])

mimic = build_java_class_mimic(
    ["MessageType", "EventNumber", "TimeDataValid", "Month", "Day", "Hour",
     "Minute", "EventType", "Parameter1", "Parameter2"])
mimic.isTimeDataValid = mimic.getTimeDataValid
JomnilinkII_EventLogData_for_test = mimic

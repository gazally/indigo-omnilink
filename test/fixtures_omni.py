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

from functools import partial
import mock
from mock import patch, Mock, MagicMock
import StringIO
from subprocess import Popen
import sys

from fixtures import (Fixture, CompositeFixture)


class Py4JError(Exception):
    pass


class PopenPatchFixture(Fixture):
    """ No Fixture Dependencies.
    Create a mock to be the return value from the java subprocess.
    """
    def setUp(self, tc):
        """ make a Mock to pretend to be the java subprocess """
        tc.javaproc_mock = Mock()
        tc.javaproc_mock.stdout = StringIO.StringIO("stdout\n")
        tc.javaproc_mock.stderr = StringIO.StringIO("")
        popen_mock = mock.create_autospec(Popen)
        popen_mock.return_value = tc.javaproc_mock
        self.popen_patcher = patch("subprocess.Popen", popen_mock)
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

JomnilinkIIFixture = CompositeFixture(PopenPatchFixture, JavaGatewayFixture)


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

JomnilinkII_SystemInformation_for_test = build_java_class_mimic(
    ["Model", "Major", "Minor", "Revision", "Phone"])

JomnilinkII_SystemTroubles_for_test = build_java_class_mimic(
    ["Troubles"])

JomnilinkII_SystemStatus_for_test = build_java_class_mimic(
    ["BatteryReading"])

JomnilinkII_ObjectProperties_for_test = build_java_class_mimic(
    ["ObjectType", "Number", "Name", "MessageType"])

JomnilinkII_ZoneProperties_for_test = build_java_class_mimic(
    ["MessageType", "Name", "Number", "ZoneType", "Area", "Options"])

JomnilinkII_UnitProperties_for_test = build_java_class_mimic(
    ["MessageType", "Name", "Number", "UnitType"])

JomnilinkII_ObjectStatus_for_test = build_java_class_mimic(
    ["StatusType", "Statuses"])

JomnilinkII_ZoneStatus_for_test = build_java_class_mimic(
    ["Number", "Status", "Loop"])

JomnilinkII_UnitStatus_for_test = build_java_class_mimic(
    ["Number", "Status", "Time"])

JomnilinkII_SecurityCodeValidation_for_test = build_java_class_mimic(
    ["CodeNumber", "AuthorityLevel"])

JomnilinkII_OtherEventNotifications_for_test = build_java_class_mimic(
    ["Notifications"])

mimic = build_java_class_mimic(
    ["MessageType", "EventNumber", "TimeDataValid", "Month", "Day", "Hour",
     "Minute", "EventType", "Parameter1", "Parameter2"])
mimic.isTimeDataValid = mimic.getTimeDataValid
JomnilinkII_EventLogData_for_test = mimic

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

# --- Prepare to import plugin.py. Since it depends on two modules, indigo and
# py4j, which should not be in the test environment because they have too
# many real world side effects, do some mocking first.

plugin_path = os.path.abspath('../Omnilink.indigoPlugin/Contents/Server Plugin')
if plugin_path not in sys.path:
    sys.path.append(plugin_path)

if 'plugin' not in sys.modules:
    sys.modules['indigo'] = indigo_mock.mock_indigo
    sys.modules['py4j'] = MagicMock()
    sys.modules['py4j.java_gateway'] = sys.modules['py4j'].java_gateway
    sys.modules['py4j.protocol'] = sys.modules['py4j'].protocol

# run tests from test directory, or this will fail 
import plugin
from plugin import Plugin

concurrent_thread_time = 0.1

class TestException(Exception):
    pass

class Py4JError(Exception):
    pass

class PluginStartupShutdownTestCase(TestCase):
    """Fixtures for test cases that get everything ready to start a
    plugin, but don't actually do so...unless you are testing the
    plugin startup and shutdown code itself, you probably want
    PluginTestCase (see below)
    """
    def setUp(self):
        # patch subprocess.pOpen
        self.applied_patches = []
        self.patch_Popen()

        # mock up the java gateway
        self.gateway_mock = Mock()
        self.py4j_mock = sys.modules['py4j']
        self.py4j_mock.java_gateway.JavaGateway.return_value = self.gateway_mock
        self.py4j_mock.protocol.Py4JError = Py4JError
        self.jomnilinkII_mock = self.gateway_mock.jvm.com.digitaldan.jomnilinkII

        # Mock up connection objects -- allow for multiple connections
        self.connection_mocks = [Mock(), Mock()]
        self.connection_mock = self.connection_mocks[0]
        self.jomnilinkII_mock.Connection.side_effect = self.connection_mocks

        # build our own callback functionality so notification and
        # disconnect listeners can be tested
        # keep separate lists for each mock connection object
        self.notify_listeners = []
        self.disconnect_listeners = []
        for i in range(len(self.connection_mocks)):
            self.connection_mocks[i].addNotificationListener.side_effect = partial(self.add_notify, i)
            self.notify_listeners.append([])
            self.connection_mocks[i].addDisconnectListener.side_effect = partial(self.add_disconnect, i)
            self.disconnect_listeners.append([])

        # reset any global state in our indigo mockup
        indigo_mock.reset()

        # indigo starts the plugin with current directory set to Server Plugin
        # so do the same here
        self.plugin_module = plugin
        os.chdir(plugin_path)

    def tearDown(self):
        # use reset_mock if you are testing an error condition
        self.assertFalse(plugin.indigo.PluginBase.errorLog.called) 
        [patch.stop() for patch in self.applied_patches]

    def patch_Popen(self):
        """ make a Mock to pretend to be the java subprocess """
        self.javaproc_mock = mock.create_autospec(subprocess.Popen)
        self.javaproc_mock.stdout = StringIO.StringIO("stdout\n")
        self.javaproc_mock.stderr = StringIO.StringIO("")
        popen_patcher = patch("plugin.subprocess.Popen",
                              Mock(return_value=self.javaproc_mock))
        popen_patcher.start()
        self.applied_patches.append(popen_patcher)
        
    def new_plugin(self):
        """ create and start a plugin object """
        props = {}
        props["showDebugInfo"] = False
        props["showJomnilinkIIDebugInfo"] = False
            
        plugin = Plugin("", "", _VERSION, props)

        # patch time.sleep to short circuit the plugin's wait for
        # its java subprocess to start
        sleep = time.sleep
        with patch('plugin.time.sleep') as ts:
            ts.side_effect = lambda t: sleep(t/100)
            plugin.startup()
        return plugin

    def add_notify(self, i, notify_listener):
        self.notify_listeners[i].append(notify_listener)

    def add_disconnect(self, i, disconnect_listener):
        self.disconnect_listeners[i].append(disconnect_listener)

    def run_concurrent_thread(self, time_limit):
        self.plugin.StopThread = TestException
        class local:
            now = 0

        def sleep(seconds):
            if local.now > time_limit:
                raise TestException("done")
            local.now += seconds

        self.plugin.sleep = sleep
        t = Thread(target=self.plugin.runConcurrentThread)
        t.setDaemon(True)
        t.start()
        time.sleep(0.1)
        self.assertFalse(t.is_alive())


class PluginTestCase(PluginStartupShutdownTestCase):
    """ Test case parent class that starts and shuts down the plugin for you """
    def setUp(self):
        PluginStartupShutdownTestCase.setUp(self)
        self.plugin = self.new_plugin()
        self.assertFalse(self.plugin.errorLog.called)

    def tearDown(self):
        self.assertFalse(self.plugin.errorLog.called)
        self.plugin.shutdown()
        PluginStartupShutdownTestCase.tearDown(self)

   # this should match the inital state in Device_Factory.xml
    dialog_flags = {"isConnected": False,
                   "error" : False,
                   "connectionError" : False,
                   "ipAddressError" : False,
                   "portNumberError" : False,
                   "encryptionKey1Error" : False,
                   "encryptionKey2Error" : False}
        
            
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
    
    
            

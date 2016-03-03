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
import sys, os
import unittest

from unittest import TestCase
from mock import patch, Mock, MagicMock
import time
from threading import Thread

_VERSION = "0.1.0"

testpath = os.getcwd()
sys.path.append(os.path.abspath('../Omnilink.indigoPlugin/Contents/Server Plugin'))
os.chdir(os.path.abspath('../Omnilink.indigoPlugin/Contents/Server Plugin'))

concurrent_thread_time = 0.5

class TestException(Exception):
    pass

class PluginBaseForTest(object):
    def __init__(self, pid, name, version, prefs):
        self.pluginPrefs = prefs

def substitute(self, string, validateOnly=False):
    if validateOnly:
        return (True, string)
    else:
        return string

class DeviceForTest(object):
    """ Mockup of indigo.device, for testing """
    def __init__(self, dev_id, name, props):
        self.id = dev_id
        self.name = name
        self.pluginProps = props
        self.states = {}
        self.configured = True
        self.enabled = True
    def updateStateOnServer(self, key=None, value=None, clearErrorState=True):
        assert key is not None
        assert value is not None
        self.states[key] = value
    def replacePluginPropsOnServer(self, props):
        self.pluginProps = props
    def refreshFromServer(self):
        pass

class IndigoDictForTest(dict):
    def iter(self, whatever):
        return self.values()


class IndigoMockTestCase(TestCase):
    """ Mock indigo so the plugin can be imported """
    def setUp(self):
        self.indigo_mock = MagicMock()
        self.indigo_mock.Dict = dict
        self.indigo_mock.PluginBase = PluginBaseForTest
        self.indigo_mock.devices = IndigoDictForTest()
        #self.indigo_mock.server.log.side_effect = print

        modules = sys.modules.copy()
        modules["indigo"] = self.indigo_mock
        self.module_patcher = patch.dict("sys.modules", modules)
        self.module_patcher.start()
        import plugin
        self.plugin_module = plugin
        self.plugin_module.indigo.PluginBase = PluginBaseForTest

    def tearDown(self):
        self.module_patcher.stop()

class PluginTestCase(IndigoMockTestCase):
    def setUp(self):
        IndigoMockTestCase.setUp(self)
        PluginBaseForTest.pluginPrefs = {u"showDebugInfo" : False}
        PluginBaseForTest.debugLog = Mock(side_effect=print)
        PluginBaseForTest.errorLog = Mock(side_effect=print)
        PluginBaseForTest.sleep = Mock()
        PluginBaseForTest.substitute = substitute

        self.plugin = self.new_plugin()
        self.assertFalse(PluginBaseForTest.errorLog.called)

    def tearDown(self):
        self.plugin.shutdown()
        PluginBaseForTest.debugLog.side_effect=None
        PluginBaseForTest.errorLog.side_effect=None
        IndigoMockTestCase.tearDown(self)

    def new_plugin(self):
        # Before I created this little function,
        # python was giving me a bizillion "NoneType object has no
        # attribute" warnings, I think because tearDown is called,
        # removing the base class, before the plugin objects are deleted.
        # why this fixed it is a mystery to me
        props = {}
        props["showDebugInfo"]=False
        with open(os.path.join(testpath, "omni.txt"), "r") as keyfile:
            # In order to test communication with your omni system, put its
            # connection parameters (ip address, port, encryption key) in a
            # three line text file called omni.txt in the test directory
            lines = keyfile.readlines()
            props["ipAddress"] = lines[0].strip()
            props["portNumber"] = lines[1].strip()
            props["encryptionKey1"] = lines[2][:23]
            props["encryptionKey2"] = lines[2][24:47]
            
        plugin = self.plugin_module.Plugin("", "", _VERSION, props)
        plugin.startup()
        self.assertFalse(PluginBaseForTest.errorLog.called)
        return plugin

    def test_DebugMenuItem_Toggles(self):
        self.assertFalse(self.plugin.debug)
        self.plugin.debugLog.reset_mock()
        self.plugin.toggleDebugging()
        self.assertEqual(self.plugin.debugLog.call_count, 1)
        self.assertTrue(self.plugin.debug)

        self.plugin.toggleDebugging()
        self.assertEqual(self.plugin.debugLog.call_count, 3)
        self.assertFalse(self.plugin.debug)
        self.assertFalse(PluginBaseForTest.errorLog.called)

    def test_PreferencesUIValidation_Succeeds_OnValidInput(self):
        values = {"showDebugInfo" : True,
                  "ipAddress" : "192.168.1.42",
                  "portNumber" : "4444",
                  "encryptionKey1" : "01-23-45-67-89-AB-CD-EF",
                  "encryptionKey2" : "01-23-45-67-89-AB-CD-EF"}
        ok, d = self.plugin.validatePrefsConfigUi(values)
        self.assertTrue(ok)
        values["showDebugInfo"] = False
        ok, d = self.plugin.validatePrefsConfigUi(values)
        self.assertTrue(ok)
        self.assertFalse(PluginBaseForTest.errorLog.called)

    def test_PreferencesUIValidation_Fails_OnInvalidInput(self):
        test_values = [
            {"showDebugInfo" : True,
              "ipAddress" : "not an ip address",
              "portNumber" : "not a port",
              "encryptionKey1" : "not an encryption key",
              "encryptionKey2" : "still not an encryption key"}
            ]
        keys = ["ipAddress", "portNumber", "encryptionKey1", "encryptionKey2"]
        for values in test_values:
            ok, d, e = self.plugin.validatePrefsConfigUi(values)
            self.assertFalse(ok)
            for k in keys:
                self.assertTrue(k in e)
                
    def test_DeviceStartComm_Succeeds_OnValidInput(self):
        dev = self.make_and_start_a_test_device(1, "dev1",
                {"deviceVersion":_VERSION})
        self.assertFalse(PluginBaseForTest.errorLog.called)

    def test_DeviceStopComm_Succeeds(self):
        dev = self.make_and_start_a_test_device(
            1, "d1",
            {"deviceVersion":_VERSION},
            time=1)

        self.plugin.deviceStopComm(dev)
        self.assertFalse(PluginBaseForTest.errorLog.called)

    def make_and_start_a_test_device(self, dev_id, name, props,
                                     time=concurrent_thread_time):
        dev = DeviceForTest(dev_id, name, props)
        self.indigo_mock.devices[dev_id] = dev
        self.plugin.deviceStartComm(dev)
        self.run_concurrent_thread(time)
        return dev

    def run_concurrent_thread(self, time_limit):
        self.plugin.StopThread = TestException
        starttime = datetime.datetime.now()
        stoptime = starttime + datetime.timedelta(seconds=time_limit)
        
        def sleep(seconds):
            now = datetime.datetime.now()
            if now > stoptime:
                raise TestException("done")
            time.sleep(seconds)

        self.plugin.sleep = sleep
        t = Thread(target=self.plugin.runConcurrentThread)
        t.start()
        t.join(time_limit + 0.3)
        self.assertFalse(t.is_alive())

    def asserts_for_UIValidation_Failure(self, tag, tup):
        self.assertEqual(len(tup), 3)
        ok, val, errs = tup
        self.assertFalse(ok)
        if tag:
            self.assertTrue(tag in errs)
            self.assertTrue(errs[tag])


if __name__ == "__main__":
    unittest.main()

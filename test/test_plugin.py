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

import unittest

from mock import Mock, MagicMock, patch

from fixtures_for_test import *

class PluginStartQuitTestCase(PluginStartupShutdownTestCase):

    def test_Creation_Handles_FailureToStartJava(self):
        with patch("plugin.subprocess.Popen", Mock(side_effect=OSError)):
            self.plugin = self.new_plugin()
            self.assertTrue(self.plugin.errorLog.called)
            self.plugin.errorLog.reset_mock()
            self.plugin.shutdown()

    def test_Shutdown_Handles_Exceptions(self):
        self.plugin = self.new_plugin()
        self.gateway_mock.shutdown.side_effect = Py4JError
        self.plugin.shutdown()
        self.assertTrue(self.plugin.errorLog.called)
        self.plugin.errorLog.reset_mock()

class PluginCoreFunctionalityTestCase(PluginTestCase):

    def test_DebugMenuItem_Toggles(self):
        self.plugin.debug = False
        self.plugin.debugLog.reset_mock()
        self.plugin.toggleDebugging()
        self.assertEqual(self.plugin.debugLog.call_count, 1)
        self.assertTrue(self.plugin.debug)

        self.plugin.toggleDebugging()
        self.assertEqual(self.plugin.debugLog.call_count, 3)
        self.assertFalse(self.plugin.debug)
        self.assertFalse(self.plugin.errorLog.called)

    def test_RunConcurrentThread_Stops(self):
        self.run_concurrent_thread(5)

    def test_JomnilinkIIDebugMenuItem_Toggles(self):
        self.plugin.debug_omni = False
        self.plugin.debugLog.reset_mock()
        self.plugin.toggleJomnilinkIIDebugging()
        self.assertEqual(self.plugin.debugLog.call_count, 1)
        self.assertTrue(self.plugin.debug_omni)

        self.plugin.toggleJomnilinkIIDebugging()
        self.assertEqual(self.plugin.debugLog.call_count, 2)
        self.assertFalse(self.plugin.debug_omni)
        self.assertFalse(self.plugin.errorLog.called)

    def test_PreferencesUIValidation_Succeeds_OnValidInput(self):
        values = {"showDebugInfo" : True,
                  "showJomnilinkIIDebugInfo" : True}
        ok, d, e = self.plugin.validatePrefsConfigUi(values)
        self.assertTrue(ok)
        values["showDebugInfo"] = False
        ok, d, e = self.plugin.validatePrefsConfigUi(values)
        self.assertTrue(ok)
        self.assertFalse(self.plugin.errorLog.called)

    # this should match the inital state in Device_Factory.xml
    dialog_flags = {"isConnected": False,
                   "error" : False,
                   "connectionError" : False,
                   "ipAddressError" : False,
                   "portNumberError" : False,
                   "encryptionKey1Error" : False,
                   "encryptionKey2Error" : False}
                   

    def test_DeviceFactoryUIValidation_Succeeds_OnValidInput(self):
        values = {"ipAddress" : "192.168.1.42",
                  "portNumber" : "4444",
                  "encryptionKey1" : "01-23-45-67-89-AB-CD-EF",
                  "encryptionKey2" : "01-23-45-67-89-AB-CD-EF"}
        values.update(self.dialog_flags)
        ok, d, e = self.plugin.validateDeviceFactoryUi(values, [])
        self.assertTrue(ok)
        self.assertFalse(self.plugin.errorLog.called)

    def test_DeviceFactoryUIValidation_Fails_OnInvalidInput(self):
        values = {"ipAddress" : "not an ip address",
                  "portNumber" : "not a port",
                  "encryptionKey1" : "not an encryption key",
                  "encryptionKey2" : "still not an encryption key"}
        values.update(self.dialog_flags)

        keys = ["ipAddress", "portNumber", "encryptionKey1", "encryptionKey2"]
        ok, d, e = self.plugin.validateDeviceFactoryUi(values, [])
        self.assertFalse(ok)
        for k in keys:
            self.assertTrue(k in e)

    def test_makeConnection_ClearsErrorState_OnValidInput(self):
        values = {"ipAddress" : "192.168.1.42",
                  "portNumber" : "4444",
                  "encryptionKey1" : "01-23-45-67-89-AB-CD-EF",
                  "encryptionKey2" : "01-23-45-67-89-AB-CD-EF"}
        errors = {"ipAddressError" : True,
                  "portError": True,
                  "encryptionKey1Error" : True,
                  "encryptionKey2Error" : True,
                  "error" : True}
        values.update(self.dialog_flags)
        values.update(errors)
        
        values = self.plugin.makeConnection(values, [])
        self.assertFalse(values["error"])
        keys = ["ipAddress", "portNumber", "encryptionKey1", "encryptionKey2"]
        for k in keys:
            self.assertFalse(values[k + "Error"])
        self.assertFalse(values["connectionError"])
        self.assertTrue(values["isConnected"])

    def test_makeConnection_SetsErrorState_OnInvalidInput(self):
        values = {"ipAddress" : "not an ip address",
                  "portNumber" : "not a port",
                  "encryptionKey1" : "not an encryption key",
                  "encryptionKey2" : "still not an encryption key"}
        values.update(self.dialog_flags)

        values = self.plugin.makeConnection(values, [])
        self.assertTrue(values["error"])
        keys = ["ipAddress", "portNumber", "encryptionKey1", "encryptionKey2"]
        for k in keys:
            self.assertTrue(values[k + "Error"])
        self.assertTrue(values["error"])
        self.assertFalse(values["isConnected"])

    def test_makeConnection_SetsErrorState_OnFailureToConnect(self):
        values = {"ipAddress" : "192.168.1.42",
                  "portNumber" : "4444",
                  "encryptionKey1" : "01-23-45-67-89-AB-CD-EF",
                  "encryptionKey2" : "01-23-45-67-89-AB-CD-EF"}
        values.update(self.dialog_flags)

        self.jomnilinkII_mock.Connection.side_effect = TestException
        values = self.plugin.makeConnection(values, [])
            
        self.assertTrue(values["error"])
        keys = ["ipAddress", "portNumber", "encryptionKey1", "encryptionKey2"]
        for k in keys:
            self.assertFalse(values[k + "Error"])
        self.assertTrue(values["connectionError"])
        self.assertFalse(values["isConnected"])
        self.assertTrue(self.plugin.errorLog.called)
        self.plugin.errorLog.reset_mock()

    def test_GetDeviceFactoryUIValues_Handles_EmptyDeviceList(self):
        values, errors = self.plugin.getDeviceFactoryUiValues([])
        self.assertEqual(len(errors), 0)
        self.assertTrue("isConnected" not in values or not values["isConnected"])

    def test_GetDeviceFactoryUIValues_MakesConnection_GivenDevice(self):
        values = {"ipAddress" : "192.168.1.42",
                  "portNumber" : "4444",
                  "encryptionKey1" : "01-23-45-67-89-AB-CD-EF",
                  "encryptionKey2" : "01-23-45-67-89-AB-CD-EF"}
        dev = self.plugin_module.indigo.device.create(Mock(), "none", values)
        
        values, errors = self.plugin.getDeviceFactoryUiValues([dev.id])
        self.assertEqual(len(errors), 0)
        self.assertTrue(values["isConnected"])


if __name__ == "__main__":
    unittest.main()

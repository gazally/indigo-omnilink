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

from fixtures import *
from fixtures_plugin import (PluginStartedFixture,
                             PluginEnvironmentFixture,
                             NewPluginFixture)
from fixtures_omni import Py4JError, ConnectionValuesFixture


class PluginStartQuitTestCase(TestCaseWithFixtures):
    """ Tests that need everything ready to create the plugin but no
    plugin created yet.
    """
    def setUp(self):
        TestCaseWithFixtures.setUp(self)
        self.useFixture(PluginEnvironmentFixture)

    def test_Creation_Handles_FailureToStartJava(self):
        with patch("connection.subprocess.Popen",
                   Mock(side_effect=OSError)):
            self.useFixture(NewPluginFixture)
            self.assertTrue(self.plugin.errorLog.called)
            self.plugin.errorLog.reset_mock()
            self.plugin.shutdown()

    def test_Shutdown_Handles_Exceptions(self):
        self.useFixture(NewPluginFixture)
        self.gateway_mock.shutdown.side_effect = Py4JError
        self.plugin.shutdown()
        self.assertTrue(self.gateway_mock.shutdown.called)
        self.assertTrue(self.plugin.errorLog.called)
        self.plugin.errorLog.reset_mock()


class PluginCoreFunctionalityTestCase(TestCaseWithFixtures):
    """ Test cases that require a started plugin """
    def setUp(self):
        TestCaseWithFixtures.setUp(self)
        self.useFixture(PluginStartedFixture)
        self.useFixture(ConnectionValuesFixture)

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
        NewPluginFixture.run_concurrent_thread(self, self.plugin, 5)

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

    def test_StartInteractiveInterpreterMenuItem_Succeeds(self):
        with patch("plugin.start_shell_thread") as p:
            self.plugin.startInteractiveInterpreter()
            self.assertTrue(p.called)

    def test_PreferencesUIValidation_Succeeds_OnValidInput(self):
        values = {"showDebugInfo": True,
                  "showJomnilinkIIDebugInfo": True}
        ok, d, e = self.plugin.validatePrefsConfigUi(values)
        self.assertTrue(ok)
        values["showDebugInfo"] = False
        ok, d, e = self.plugin.validatePrefsConfigUi(values)
        self.assertTrue(ok)
        self.assertFalse(self.plugin.errorLog.called)

    def test_DeviceFactoryUIValidation_Succeeds_OnValidInput(self):
        ok, d, e = self.plugin.validateDeviceFactoryUi(self.values, [])
        self.assertTrue(ok)
        self.assertFalse(self.plugin.errorLog.called)

    def test_DeviceFactoryUIValidation_Fails_OnInvalidInput(self):
        values = {"ipAddress": "not an ip address",
                  "portNumber": "not a port",
                  "encryptionKey1": "not an encryption key",
                  "encryptionKey2": "still not an encryption key"}
        values.update(ConnectionValuesFixture.device_factory_dialog_flags)

        keys = ["ipAddress", "portNumber", "encryptionKey1", "encryptionKey2"]
        ok, d, e = self.plugin.validateDeviceFactoryUi(values, [])
        self.assertFalse(ok)
        for k in keys:
            self.assertTrue(k in e)

    def test_makeConnection_ClearsErrorState_OnValidInput(self):
        errors = {"ipAddressError": True,
                  "portError": True,
                  "encryptionKey1Error": True,
                  "encryptionKey2Error": True,
                  "error": True}
        self.values.update(errors)

        values = self.plugin.makeConnection(self.values, [])
        self.assertFalse(values["error"])
        keys = ["ipAddress", "portNumber", "encryptionKey1", "encryptionKey2"]
        for k in keys:
            self.assertFalse(values[k + "Error"])
        self.assertFalse(values["connectionError"])
        self.assertTrue(values["isConnected"])

    def test_makeConnection_SetsErrorState_OnInvalidInput(self):
        values = {"ipAddress": "not an ip address",
                  "portNumber": "not a port",
                  "encryptionKey1": "not an encryption key",
                  "encryptionKey2": "still not an encryption key"}
        values.update(ConnectionValuesFixture.device_factory_dialog_flags)

        values = self.plugin.makeConnection(values, [])
        self.assertTrue(values["error"])
        keys = ["ipAddress", "portNumber", "encryptionKey1", "encryptionKey2"]
        for k in keys:
            self.assertTrue(values[k + "Error"])
        self.assertTrue(values["error"])
        self.assertFalse(values["isConnected"])

    def test_makeConnection_SetsErrorState_OnFailureToConnect(self):
        self.jomnilinkII_mock.Connection.side_effect = TestException
        values = self.plugin.makeConnection(self.values, [])

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
        self.assertTrue("isConnected" not in values or
                        not values["isConnected"])

    def test_GetDeviceFactoryUIValues_MakesConnection_GivenDevice(self):
        dev = self.plugin_module.indigo.device.create(Mock(),
                                                      "omniControllerDevice",
                                                      self.values)

        values, errors = self.plugin.getDeviceFactoryUiValues([dev.id])
        self.assertEqual(len(errors), 0)
        self.assertTrue(values["isConnected"])


if __name__ == "__main__":
    unittest.main()

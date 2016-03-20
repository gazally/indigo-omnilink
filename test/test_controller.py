#! /usr/bin/env python
# Unit Tests for controller extension to Omnilink Plugin for Indigo Server
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

from mock import Mock, MagicMock

from fixtures_for_test import *

import indigo  # This must come after fixtures_for_test because it
               # is mocked up by fixtures_for_test

class ControllerDeviceTestCase(PluginTestCase):
    def setUp(self):
        PluginTestCase.setUp(self)

    def test_GetDeviceList_ReturnsController(self):
        values = {"ipAddress" : "192.168.1.42",
                  "portNumber" : "4444",
                  "encryptionKey1" : "01-23-45-67-89-AB-CD-EF",
                  "encryptionKey2" : "01-23-45-67-89-AB-CD-EF",
                  "prefix":""}
        values.update(self.dialog_flags)
        values = self.plugin.makeConnection(values, [])
        result = self.plugin.getDeviceGroupList(None, values, [])
        self.assertTrue(("omniControllerDevice", "Controller") in result)

    def test_CreateDevices_CreatesOnlyOneController(self):
        pass
        values = {"ipAddress" : "192.168.1.42",
                  "portNumber" : "4444",
                  "encryptionKey1" : "01-23-45-67-89-AB-CD-EF",
                  "encryptionKey2" : "01-23-45-67-89-AB-CD-EF",
                  "prefix" : ""}
        values.update(self.dialog_flags)
        values = self.plugin.makeConnection(values, [])
        values["deviceGroupList"] = ["omniControllerDevice"]
        self.plugin.createDevices(values, [dev.id for dev in indigo.devices.values()])
        self.assertEqual(len(set([dev for dev in indigo.devices.values()
                                  if dev.deviceTypeId == "omniControllerDevice"])), 1)

        self.plugin.createDevices(values, [dev.id for dev in indigo.devices.values()])

        self.assertEqual(len(set([dev for dev in indigo.devices.values()
                                  if dev.deviceTypeId == "omniControllerDevice"])), 1)

    def test_DeviceStartComm_Succeeds(self):
        self.mock_JomnilinkII_messages_for_deviceStartComm()
        dev = self.create_controller_device()

        self.plugin.deviceStartComm(dev)
        self.assertFalse(self.plugin.errorLog.called)

        self.assertEqual(dev.states["connected"], True)
        self.assertEqual(dev.states["model"], "HAI Omni IIe")
        self.assertEqual(dev.states["firmwareVersion"], "2.16b")
        self.assertEqual(dev.states["batteryReading"], 200)
        troubles = {"freezeTrouble": True,
                    "batteryLowTrouble": True,
                    "ACPowerTrouble": True,
                    "phoneLineTrouble": True,
                    "digitalCommunicatorTrouble" : False,
                     "fuseTrouble":False}
        for t, val in troubles.items():
            self.assertEqual(dev.states[t], val)

    def mock_JomnilinkII_messages_for_deviceStartComm(self, i=0):
        self.connection_mocks[i].reqSystemInformation = Mock(
            return_value = JomnilinkII_SystemInformation_for_test(30, 2, 16, 2, ""))
        self.connection_mocks[i].reqSystemStatus = Mock(
            return_value = JomnilinkII_SystemStatus_for_test(200))
        self.connection_mocks[i].reqSystemTroubles = Mock(
            return_value = JomnilinkII_SystemTroubles_for_test([1, 2, 3, 4]))

    def test_DeviceStartComm_Fails_OnNetworkError(self):
        self.connection_mock.reqSystemInformation = Mock(
            side_effect = self.plugin_module.extensions.ConnectionError)
        dev = self.create_controller_device()
        self.plugin.deviceStartComm(dev)
        self.assertTrue(dev.error_state is not None)
        self.assertTrue(self.plugin.errorLog.called)
        self.plugin.errorLog.reset_mock()

    def test_DeviceStopComm_Succeeds(self):
        self.connection_mock.reqSystemInformation = Mock(
            return_value = JomnilinkII_SystemInformation_for_test(37, 3, 0, 254, ""))
        self.connection_mock.reqSystemStatus = Mock(
            return_value = JomnilinkII_SystemStatus_for_test(0))
        self.connection_mock.reqSystemTroubles = Mock(
            return_value = JomnilinkII_SystemTroubles_for_test([5, 6]))
        dev = self.create_controller_device()
        self.plugin.deviceStartComm(dev)
        self.assertFalse(self.plugin.errorLog.called)
        self.assertEqual(dev.states["connected"], True)
        self.assertEqual(dev.states["model"], "HAI Lumina Pro")
        self.assertEqual(dev.states["firmwareVersion"], "3.0X2")
        troubles = {"freezeTrouble": False,
                    "batteryLowTrouble": False,
                    "ACPowerTrouble": False,
                    "phoneLineTrouble": False,
                    "digitalCommunicatorTrouble" : True,
                     "fuseTrouble":True}
        for t, val in troubles.items():
            self.assertEqual(dev.states[t], val)
        self.plugin.deviceStopComm(dev)

    def create_controller_device(self, values=None):
        if values is None:
            values = {"ipAddress" : "192.168.1.42",
                      "portNumber" : "4444",
                      "encryptionKey1" : "01-23-45-67-89-AB-CD-EF",
                      "encryptionKey2" : "01-23-45-67-89-AB-CD-EF",
                      "prefix" : ""}
        values.update(self.dialog_flags)
        values = self.plugin.makeConnection(values, [])
        values["deviceGroupList"] = ["omniControllerDevice"]
        self.plugin.createDevices(values, [dev.id for dev in set(indigo.devices.values())
                                           if dev.pluginProps["ipAddress"] == values["ipAddress"]])
        dev = [dev for dev in indigo.devices.values()
               if (dev.deviceTypeId == "omniControllerDevice" and
                   dev.pluginProps["ipAddress"] == values["ipAddress"])][0]
        return dev

    def test_DisconnectNotification_SetsErrorState_OfCorrectControllerDevice(self):
        for i in range(2):
            self.mock_JomnilinkII_messages_for_deviceStartComm(i)
        dev1 = self.create_controller_device()
        values = {"ipAddress": "10.0.0.2",
                  "portNumber" : "4444",
                  "encryptionKey1" : "01-23-45-67-89-AB-CD-EF",
                  "encryptionKey2" : "01-23-45-67-89-AB-CD-EF",
                  "prefix" : ""}
        dev2 = self.create_controller_device(values)
        self.plugin.deviceStartComm(dev1)
        self.plugin.deviceStartComm(dev2)
        for listener in self.disconnect_listeners[1]:
            listener.notConnectedEvent(Mock())
        self.assertTrue(dev2.error_state is not None)

    def test_ReconnectNotification_Clears_DeviceErrorState(self):
        for i in range(2):
            self.mock_JomnilinkII_messages_for_deviceStartComm(i)
        dev = self.create_controller_device()
        self.plugin.deviceStartComm(dev)
        self.assertFalse(dev.states["digitalCommunicatorTrouble"])

        self.connection_mocks[0].connected.return_value = False
        for listener in self.disconnect_listeners[0]:
            listener.notConnectedEvent(Mock())

        self.assertTrue(dev.error_state is not None)
        self.connection_mocks[1].reqSystemTroubles = Mock(
            return_value = JomnilinkII_SystemTroubles_for_test([5, 6]))

        self.plugin.update() # this should get the second connection object
        self.assertTrue(dev.error_state is None)
        self.assertTrue(dev.states["digitalCommunicatorTrouble"])


if __name__ == "__main__":
    unittest.main()

#! /usr/bin/env python
# Unit Tests for zones extension to Omnilink Plugin for Indigo Server
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

class ZoneDeviceTestCase(PluginTestCase):
    def setUp(self):
        PluginTestCase.setUp(self)
        for i in range(len(self.connection_mocks)):
            self.connection_mocks[i].reqObjectProperties = self.create_reqObjProperties_Mock()
            self.connection_mocks[i].reqObjectStatus = self.create_reqObjStatus_Mock()

    def test_GetDeviceList_ReturnsZone(self):
        values = {"ipAddress" : "192.168.1.42",
                  "portNumber" : "4444",
                  "encryptionKey1" : "01-23-45-67-89-AB-CD-EF",
                  "encryptionKey2" : "01-23-45-67-89-AB-CD-EF",
                  "prefix":""}
        values.update(self.dialog_flags)
        values = self.plugin.makeConnection(values, [])
        result = self.plugin.getDeviceGroupList(None, values, [])
        self.assertTrue(("omniZoneDevice", "Zone") in result)

    def test_GetDeviceList_ReturnsEmptyList_OnConnectionError(self):
        values = {"ipAddress" : "192.168.1.42",
                  "portNumber" : "4444",
                  "encryptionKey1" : "01-23-45-67-89-AB-CD-EF",
                  "encryptionKey2" : "01-23-45-67-89-AB-CD-EF",
                  "prefix":""}
        values.update(self.dialog_flags)
        values = self.plugin.makeConnection(values, [])
        self.connection_mock.reqObjectProperties.side_effect = self.plugin_module.extensions.ConnectionError
        result = self.plugin.getDeviceGroupList(None, values, [])
        self.assertTrue(("omniZoneDevice", "Zone") not in result)
        self.assertTrue(self.plugin.errorLog.called)
        self.plugin.errorLog.reset_mock()

    def test_CreateDevices_CreatesDeviceForEachZone(self):
        values = self.create_zone_devices()
        self.assertEqual(len(set([dev for dev in indigo.devices.values()
                                  if dev.deviceTypeId == "omniZoneDevice"])), 3)

        self.plugin.createDevices(values, [dev.id for dev in indigo.devices.values()])

        devices = set([dev for dev in indigo.devices.values()
                       if dev.deviceTypeId == "omniZoneDevice"])
        self.assertEqual(len(devices), 3)

    def create_zone_devices(self, values=None):
        if values is None:
            values = {"ipAddress" : "192.168.1.42",
                      "portNumber" : "4444",
                      "encryptionKey1" : "01-23-45-67-89-AB-CD-EF",
                      "encryptionKey2" : "01-23-45-67-89-AB-CD-EF",
                      "prefix" : ""}
        values.update(self.dialog_flags)
        values = self.plugin.makeConnection(values, [])
        values["deviceGroupList"] = ["omniZoneDevice"]
        self.plugin.createDevices(values, [dev.id for dev in indigo.devices.values()
                                           if dev.pluginProps["ipAddress"] == values["ipAddress"]])
        return values

    def create_reqObjProperties_Mock(self):
        self.jomnilinkII_mock.Message.MESG_TYPE_OBJ_PROP = 0x21
        m1 = JomnilinkII_ZoneProperties_for_test(0x21, "Front Door", 1, 1, 1, 0)
        m2 = JomnilinkII_ZoneProperties_for_test(0x21, "Motion", 2, 3, 1, 1)
        m3 = JomnilinkII_ZoneProperties_for_test(0x21, "Smoke Det", 3, 32, 1, 3)
        m4 = JomnilinkII_ZoneProperties_for_test(0, "", 0, 0, 0, 0)
        reqfunc = Mock(side_effect = [m1, m2, m3, m4])
        return reqfunc

    def create_reqObjStatus_Mock(self):
        reqfunc = Mock(return_value = JomnilinkII_ObjectStatus_for_test(
            self.jomnilinkII_mock.Message.OBJ_TYPE_ZONE,
            [JomnilinkII_ZoneStatus_for_test(0, 0, 100)]))
        return reqfunc

    def test_DeviceStartComm_Succeeds_OnValidInput(self):
        self.create_zone_devices()
        dev = indigo.devices["Smoke Det"]
        self.plugin.deviceStartComm(dev)
        self.assertTrue(dev.error_state is None)
        self.assertEqual(dev.states["name"], "Smoke Det")
        self.assertEqual(dev.states["type"], "Fire")
        self.assertEqual(dev.states["area"], 1)
        self.assertEqual(dev.states["crossZoning"], True)
        self.assertEqual(dev.states["swingerShutdown"], True)
        self.assertEqual(dev.states["dialOutDelay"], False)
        self.assertEqual(dev.states["loop"], 100)
        self.assertEqual(dev.states["condition"], "Secure")
        self.assertEqual(dev.states["alarmStatus"], "Secure")
        self.assertEqual(dev.states["armingStatus"], "Disarmed")
        self.assertEqual(dev.states["hadTrouble"], False)

    def test_DeviceStartComm_SetsErrorState_OnConnectionError(self):
        self.create_zone_devices()
        dev = indigo.devices["Smoke Det"]
        self.connection_mock.reqObjectStatus.side_effect = Py4JError

        self.plugin.deviceStartComm(dev)
        self.assertTrue(dev.error_state is not None)
        self.assertTrue(self.plugin.errorLog.called)
        self.plugin.errorLog.reset_mock()

    def test_RemoveDevices_Removes_ZoneDevices(self):
        values = self.create_zone_devices()
        dev_ids = set([dev.id for dev in indigo.devices.values()
                       if dev.deviceTypeId == "omniZoneDevice"])
        self.plugin.removeDevices(values, list(dev_ids))
        for dev in indigo.devices.values():
            self.assertNotEqual(dev.deviceTypeId, "omniZoneDevice")

    def test_Notification_Changes_DeviceState(self):
        self.create_zone_devices()
        dev = indigo.devices["Front Door"]
        self.plugin.deviceStartComm(dev)
        self.assertTrue(dev.states["condition"] == "Secure")
        self.assertFalse(self.plugin.errorLog.called)

        status_msg = JomnilinkII_ObjectStatus_for_test(
            self.jomnilinkII_mock.Message.OBJ_TYPE_ZONE,
            [JomnilinkII_ZoneStatus_for_test(1, 1, 100)])

        for listener in self.notify_listeners[0]:
            listener.objectStausNotification(status_msg)

        self.assertTrue(dev.states["condition"] == "Not Ready")
        self.assertTrue(dev.error_state is None)

    def test_Notification_Ignores_NonZoneNotifications(self):
        status_msg = JomnilinkII_ObjectStatus_for_test(
            Mock(),
            [JomnilinkII_ZoneStatus_for_test(10, 1, 100)])
        self.create_zone_devices()
        for listener in self.notify_listeners[0]:
            listener.objectStausNotification(status_msg)

    def test_DisconnectNotification_SetsErrorState_OfCorrectZoneDevice(self):
        values = self.create_zone_devices()
        devs_1 = set([dev for dev in indigo.devices.values()
                      if dev.pluginProps["ipAddress"] == values["ipAddress"]])
        values = {"ipAddress": "10.0.0.2",
                  "portNumber" : "4444",
                  "encryptionKey1" : "01-23-45-67-89-AB-CD-EF",
                  "encryptionKey2" : "01-23-45-67-89-AB-CD-EF",
                  "prefix" : ""}
        self.create_zone_devices(values)
        devs_2 = set([dev for dev in indigo.devices.values()
                      if dev.pluginProps["ipAddress"] == values["ipAddress"]])

        for dev in devs_1.union(devs_2):
            self.plugin.deviceStartComm(dev)

        for listener in self.disconnect_listeners[1]:
            listener.notConnectedEvent(Mock())

        for dev in devs_2:
            self.assertTrue(dev.error_state is not None)

    def test_ReconnectNotification_Clears_DeviceErrorState(self):
        values = self.create_zone_devices()
        devs = set([dev for dev in indigo.devices.values()
                      if dev.pluginProps["ipAddress"] == values["ipAddress"]])
        for dev in devs:
            self.plugin.deviceStartComm(dev)

        self.connection_mocks[0].connected.return_value = False
        for listener in self.disconnect_listeners[0]:
            listener.notConnectedEvent(Mock())

        self.assertTrue(dev.error_state is not None)
        self.plugin.update() # this should get the second connection object
        self.assertTrue(dev.error_state is None)

    def test_DeviceStopComm_Succeeds(self):
        self.create_zone_devices()
        dev = indigo.devices["Motion"]
        self.plugin.deviceStartComm(dev)
        self.plugin.deviceStopComm(dev)

if __name__ == "__main__":
    unittest.main()

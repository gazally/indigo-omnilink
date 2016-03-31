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

from fixtures import Fixture, CompositeFixture, TestCaseWithFixtures
from fixtures_omni import *
from fixtures_plugin import PluginStartedFixture


class MockObjPropAndStatusFixture(Fixture):
    """ Depends on MockConnectionFixture """
    def setUp(self, tc):
        for cm in tc.connection_mocks:
            cm.reqObjectProperties.side_effect = self.create_reqObjProperties(
                tc)
            cm.reqObjectStatus = self.create_reqObjStatus_Mock(tc)

    def create_reqObjProperties(self, tc):
        tc.jomnilinkII_mock.Message.MESG_TYPE_OBJ_PROP = 33

        class locals:
            i = 0

        def reqfunc(mtype, a, b, c, d, e):
            m1 = JomnilinkII_ZoneProperties_for_test(
                33, "Front Door", 1, 1, 1, 0)
            m2 = JomnilinkII_ZoneProperties_for_test(
                33, "Motion", 2, 3, 1, 1)
            m3 = JomnilinkII_ZoneProperties_for_test(
                33, "Smoke Det", 3, 32, 1, 3)
            m4 = JomnilinkII_ZoneProperties_for_test(0, "", 0, 0, 0, 0)
            if mtype != tc.jomnilinkII_mock.Message.OBJ_TYPE_ZONE:
                return m4
            else:
                result = [m1, m2, m3, m4][locals.i % 4]
                locals.i += 1
                return result

        return reqfunc

    def create_reqObjStatus_Mock(self, tc):
        os_for_test = JomnilinkII_ObjectStatus_for_test(
            tc.jomnilinkII_mock.Message.OBJ_TYPE_ZONE,
            [JomnilinkII_ZoneStatus_for_test(0, 0, 100)])

        return Mock(return_value=os_for_test)


class CreateZoneDevicesFixture(Fixture):
    """ Depends on MockObjPropAndStatusFixture, PluginStartedFixture,
    ConnectionValuesFixture
    """
    def setUp(self, tc):
        self.create_zone_devices(tc)

    @staticmethod
    def create_zone_devices(tc, values=None):
        if values is None:
            values = tc.values
        values = tc.plugin.makeConnection(values, [])
        values["deviceGroupList"] = ["omniZoneDevice"]
        indigo = tc.plugin_module.indigo
        tc.plugin.createDevices(
            values,
            [dev.id for dev in indigo.devices.values()
             if dev.pluginProps["ipAddress"] == values["ipAddress"]])
        return values

ReadyToCreateZoneDevicesFixture = CompositeFixture(MockConnectionFixture,
                                                   MockObjPropAndStatusFixture,
                                                   ConnectionValuesFixture)
ZoneDevicesCreatedFixture = CompositeFixture(ReadyToCreateZoneDevicesFixture,
                                             CreateZoneDevicesFixture)


class GetDeviceListTestCase(TestCaseWithFixtures):
    def setUp(self):
        TestCaseWithFixtures.setUp(self)
        self.useFixture(PluginStartedFixture)
        self.useFixture(ReadyToCreateZoneDevicesFixture)

    def test_GetDeviceList_ReturnsZone(self):
        self.plugin.makeConnection(self.values, [])
        result = self.plugin.getDeviceGroupList(None, self.values, [])
        self.assertTrue(self.connection_mock.reqObjectProperties.called)
        self.assertTrue(("omniZoneDevice", "Zone") in result)

    def test_GetDeviceList_ReturnsEmptyList_OnConnectionError(self):
        self.plugin.makeConnection(self.values, [])

        cm = self.connection_mock
        ConnectionError = self.plugin_module.ConnectionError
        cm.reqObjectProperties.side_effect = ConnectionError

        result = self.plugin.getDeviceGroupList(None, self.values, [])

        self.assertTrue(("omniZoneDevice", "Zone") not in result)
        self.assertTrue(self.plugin.errorLog.called)
        self.plugin.errorLog.reset_mock()

    def test_Notification_Ignores_NonZoneNotifications(self):
        status_msg = JomnilinkII_ObjectStatus_for_test(
            Mock(),
            [JomnilinkII_ZoneStatus_for_test(10, 1, 100)])
        CreateZoneDevicesFixture.create_zone_devices(self)
        for listener in self.notify_listeners[0]:
            listener.objectStausNotification(status_msg)


class ZoneDeviceTestCase(TestCaseWithFixtures):
    def setUp(self):
        TestCaseWithFixtures.setUp(self)
        self.useFixture(PluginStartedFixture)
        self.useFixture(ZoneDevicesCreatedFixture)

    def test_CreateDevices_CreatesDeviceForEachZone(self):
        indigo = self.plugin_module.indigo
        self.assertEqual(len(set([dev for dev in indigo.devices.values()
                                  if dev.deviceTypeId == "omniZoneDevice"])),
                         3)

        self.plugin.createDevices(self.values,
                                  [dev.id for dev in indigo.devices.values()])

        devices = set([dev for dev in indigo.devices.values()
                       if dev.deviceTypeId == "omniZoneDevice"])
        self.assertEqual(len(devices), 3)

    def test_DeviceStartComm_Succeeds_OnValidInput(self):
        dev = self.plugin_module.indigo.devices["Smoke Det"]
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
        dev = self.plugin_module.indigo.devices["Smoke Det"]
        self.connection_mock.reqObjectStatus.side_effect = Py4JError

        self.plugin.deviceStartComm(dev)
        self.assertTrue(dev.error_state is not None)
        self.assertTrue(self.plugin.errorLog.called)
        self.plugin.errorLog.reset_mock()

    def test_RemoveDevices_Removes_ZoneDevices(self):
        indigo = self.plugin_module.indigo
        dev_ids = set([dev.id for dev in indigo.devices.values()
                       if dev.deviceTypeId == "omniZoneDevice"])
        self.plugin.removeDevices(self.values, list(dev_ids))
        for dev in indigo.devices.values():
            self.assertNotEqual(dev.deviceTypeId, "omniZoneDevice")

    def test_Notification_Changes_DeviceState(self):
        indigo = self.plugin_module.indigo
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

    def test_DisconnectNotification_SetsErrorState_OfCorrectZoneDevice(self):
        indigo = self.plugin_module.indigo
        devs_1 = set(
            [dev for dev in indigo.devices.values()
             if dev.pluginProps["ipAddress"] == self.values["ipAddress"]])
        CreateZoneDevicesFixture.create_zone_devices(self, self.values2)
        devs_2 = set(
            [dev for dev in indigo.devices.values()
             if dev.pluginProps["ipAddress"] == self.values2["ipAddress"]])
        self.assertTrue(len(devs_2), 3)

        for dev in devs_1.union(devs_2):
            self.plugin.deviceStartComm(dev)

        for listener in self.disconnect_listeners[1]:
            listener.notConnectedEvent(Mock())

        for dev in devs_2:
            self.assertTrue(dev.error_state is not None)

    def test_ReconnectNotification_Clears_DeviceErrorState(self):
        indigo = self.plugin_module.indigo
        devs = set(
            [dev for dev in indigo.devices.values()
             if dev.pluginProps["ipAddress"] == self.values["ipAddress"]])
        for dev in devs:
            self.plugin.deviceStartComm(dev)

        self.connection_mocks[0].connected.return_value = False
        for listener in self.disconnect_listeners[0]:
            listener.notConnectedEvent(Mock())

        self.assertTrue(dev.error_state is not None)
        self.plugin.update()  # this should get the second connection object
        self.assertTrue(dev.error_state is None)

    def test_DeviceStopComm_Succeeds(self):
        dev = self.plugin_module.indigo.devices["Motion"]
        self.plugin.deviceStartComm(dev)
        self.plugin.deviceStopComm(dev)

if __name__ == "__main__":
    unittest.main()

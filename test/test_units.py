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
from fixtures import TestException
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
            m1 = JomnilinkII_UnitProperties_for_test(33, "X10 Unit", 1, 1)
            m2 = JomnilinkII_UnitProperties_for_test(33, "Radio RA", 2, 8)
            m3 = JomnilinkII_UnitProperties_for_test(33, "Voltage", 3, 13)
            m4 = JomnilinkII_UnitProperties_for_test(0, "", 0, 0, 0, 0)
            if mtype != tc.jomnilinkII_mock.Message.OBJ_TYPE_UNIT:
                return m4
            else:
                result = [m1, m2, m3, m4][locals.i % 4]
                locals.i += 1
                return result

        return reqfunc

    # this is what createReqObjProperties is setting up
    unit_types = ["omniStandardX10Unit", "omniRadioRAUnit", "omniVoltageUnit"]

    def create_reqObjStatus_Mock(self, tc):
        os_for_test = JomnilinkII_ObjectStatus_for_test(
            tc.jomnilinkII_mock.Message.OBJ_TYPE_UNIT,
            [JomnilinkII_UnitStatus_for_test(0, 0, 0)])

        return Mock(return_value=os_for_test)


class CreateUnitDevicesFixture(Fixture):
    """ Depends on MockObjPropAndStatusFixture, PluginStartedFixture,
    ConnectionValuesFixture
    """
    def setUp(self, tc):
        self.tc = tc
        self.create_unit_devices(tc)

    @staticmethod
    def create_unit_devices(tc, values=None):
        if values is None:
            values = tc.values
        values = tc.plugin.makeConnection(values, [])
        values["deviceGroupList"] = ["omniStandardX10Unit", "omniRadioRAUnit",
                                     "omniFlagUnit", "omniVoltageUnit"]
        values["prefix"] = "test"
        indigo = tc.plugin_module.indigo
        tc.plugin.createDevices(
            values,
            [dev.id for dev in indigo.devices.values()
             if dev.pluginProps["ipAddress"] == values["ipAddress"]])
        return values

    @staticmethod
    def get_unit_devices(tc):
        indigo = tc.plugin_module.indigo
        return list(set((dev for dev in indigo.devices.values()
                         if dev.deviceTypeId in
                         MockObjPropAndStatusFixture.unit_types)))


ReadyToCreateUnitDevicesFixture = CompositeFixture(MockConnectionFixture,
                                                   MockObjPropAndStatusFixture,
                                                   ConnectionValuesFixture)
UnitDevicesCreatedFixture = CompositeFixture(ReadyToCreateUnitDevicesFixture,
                                             CreateUnitDevicesFixture)


class GetDeviceListTestCase(TestCaseWithFixtures):
    def setUp(self):
        TestCaseWithFixtures.setUp(self)
        self.useFixture(PluginStartedFixture)
        self.useFixture(ReadyToCreateUnitDevicesFixture)

    def test_GetDeviceList_ReturnsUnit(self):
        self.plugin.makeConnection(self.values, [])
        result = self.plugin.getDeviceGroupList(None, self.values, [])
        self.assertTrue(self.connection_mock.reqObjectProperties.called)
        for t in MockObjPropAndStatusFixture.unit_types:
            self.assertTrue(t in [k for k, v in result])

    def test_GetDeviceList_ReturnsEmptyList_OnConnectionError(self):
        self.plugin.makeConnection(self.values, [])

        cm = self.connection_mock
        ConnectionError = self.plugin_module.ConnectionError
        cm.reqObjectProperties.side_effect = ConnectionError

        result = self.plugin.getDeviceGroupList(None, self.values, [])

        for t in MockObjPropAndStatusFixture.unit_types:
            self.assertTrue(t not in [k for k, v in result])
        self.assertTrue(self.plugin.errorLog.called)
        self.plugin.errorLog.reset_mock()

    def test_Notification_Ignores_NonUnitNotifications(self):
        status_msg = JomnilinkII_ObjectStatus_for_test(
            Mock(), [Mock(side_effect=TestException)])
        CreateUnitDevicesFixture.create_unit_devices(self)
        for listener in self.notify_listeners[0]:
            listener.objectStausNotification(status_msg)


class UnitDeviceTestCase(TestCaseWithFixtures):
    def setUp(self):
        TestCaseWithFixtures.setUp(self)
        self.useFixture(PluginStartedFixture)
        self.useFixture(UnitDevicesCreatedFixture)

    def test_CreateDevices_CreatesDeviceForEachUnit(self):
        devices = CreateUnitDevicesFixture.get_unit_devices(self)
        self.assertEqual(len(devices), 3)

        self.plugin.createDevices(self.values, [dev.id for dev in devices])

        devices = CreateUnitDevicesFixture.get_unit_devices(self)
        self.assertEqual(len(devices), 3)

    def test_DeviceStartComm_Succeeds_OnValidInput(self):
        dev = self.plugin_module.indigo.devices["test X10 Unit"]
        self.plugin.deviceStartComm(dev)
        self.assertTrue(dev.error_state is None)
        self.assertEqual(dev.states["name"], "X10 Unit")
        self.assertEqual(dev.states["onOffState"], False)
        self.assertEqual(dev.states["brightnessLevel"], 0)
        self.assertEqual(dev.states["timeLeftSeconds"], 0)

    def test_DeviceStartComm_SetsErrorState_OnConnectionError(self):
        dev = self.plugin_module.indigo.devices["test X10 Unit"]
        self.connection_mock.reqObjectStatus.side_effect = Py4JError

        self.plugin.deviceStartComm(dev)
        self.assertTrue(dev.error_state is not None)
        self.assertTrue(self.plugin.errorLog.called)
        self.plugin.errorLog.reset_mock()

    def test_RemoveDevices_Removes_UnitDevices(self):
        dev_ids = [dev.id for dev in
                   CreateUnitDevicesFixture.get_unit_devices(self)]
        self.assertTrue(len(dev_ids) > 0)
        self.plugin.removeDevices(self.values, dev_ids)
        devices = CreateUnitDevicesFixture.get_unit_devices(self)
        self.assertEqual(len(devices), 0)

    def test_Notification_Changes_DeviceState(self):
        indigo = self.plugin_module.indigo
        dev = indigo.devices["test Radio RA"]
        self.plugin.deviceStartComm(dev)
        self.assertFalse(dev.states["onOffState"])
        self.assertEqual(dev.states["brightnessLevel"], 0)
        self.assertFalse(self.plugin.errorLog.called)

        status_msg = JomnilinkII_ObjectStatus_for_test(
            self.jomnilinkII_mock.Message.OBJ_TYPE_UNIT,
            [JomnilinkII_UnitStatus_for_test(2, 1, 100)])

        for listener in self.notify_listeners[0]:
            listener.objectStausNotification(status_msg)

        self.assertTrue(dev.states["onOffState"])
        self.assertEqual(dev.states["brightnessLevel"], 1)
        self.assertEqual(dev.states["timeLeftSeconds"], 100)
        self.assertTrue(dev.error_state is None)

    def test_DisconnectNotification_SetsErrorState_OfCorrectUnitDevice(self):
        indigo = self.plugin_module.indigo
        devs_1 = set(
            [dev for dev in indigo.devices.values()
             if dev.pluginProps["ipAddress"] == self.values["ipAddress"]])
        CreateUnitDevicesFixture.create_unit_devices(self, self.values2)
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
        dev = self.plugin_module.indigo.devices["test Voltage"]
        self.plugin.deviceStartComm(dev)
        self.plugin.deviceStopComm(dev)

    def test_actionCommandDimmerRelay_SendsCommands(self):
        dev = self.plugin_module.indigo.devices["test Radio RA"]
        self.plugin.deviceStartComm(dev)

        action = Mock()
        k = self.plugin_module.indigo.kDimmerRelayAction
        actions = ["TurnOn", "TurnOff", "Toggle", "SetBrightness",
                   "BrightenBy", "DimBy"]
        params = [0, 0, 0, 40, 20, 30]
        for i, a, p in zip(range(len(actions)), actions, params):
            setattr(k, a, i)
            action.deviceAction = i
            action.actionValue = params[i]
            self.plugin.actionControlDimmerRelay(action, dev)

        self.assertEqual(self.connection_mock.controllerCommand.call_count,
                         len(actions))


if __name__ == "__main__":
    unittest.main()

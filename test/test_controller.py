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

# This must come after fixtures_for_test because it is mocked up by
# fixtures_for_test
import indigo

_VERSION = "0.2.0"


class ControllerDeviceFixture(Fixture):
    """ Fixture dependencies: PluginStartedFixture and ConnectionValuesFixture
    Create a controller device, and set up the jomnilinkII mock
    to handle reqSystemInformation, reqSystemStatus and reqSystemTroubles.
    """
    def setUp(self, tc):
        self.mock_JomnilinkII_messages_for_deviceStartComm(tc)
        tc.dev = self.create_controller_device(tc)

    def mock_JomnilinkII_messages_for_deviceStartComm(self, tc):
        for cm in tc.connection_mocks:
            cm.reqSystemInformation = Mock(
                return_value=JomnilinkII_SystemInformation_for_test(30, 2, 16,
                                                                    2, ""))
            cm.reqSystemStatus = Mock(
                return_value=JomnilinkII_SystemStatus_for_test(200))
            cm.reqSystemTroubles = Mock(
                return_value=JomnilinkII_SystemTroubles_for_test([1, 2, 3, 4]))

    @staticmethod
    def create_controller_device(tc, values=None):
        if values is None:
            values = tc.values
        values = tc.plugin.makeConnection(values, [])
        values["deviceGroupList"] = ["omniControllerDevice"]
        tc.plugin.createDevices(
            values,
            [dev.id for dev in set(indigo.devices.values())
             if dev.pluginProps["ipAddress"] == values["ipAddress"]])
        dev = [dev for dev in indigo.devices.values()
               if (dev.deviceTypeId == "omniControllerDevice" and
                   dev.pluginProps["ipAddress"] == values["ipAddress"])][0]
        return dev


class ControllerDeviceStartFixture(Fixture):
    """ Fixture dependencies: ControllerDeviceFixture
    Start the device that ControllerDeviceFixture made
    """
    def setUp(self, tc):
        tc.plugin.deviceStartComm(tc.dev)

ControllerDeviceStartedFixture = CompositeFixture(PluginStartedFixture,
                                                  ConnectionValuesFixture,
                                                  ControllerDeviceFixture,
                                                  ControllerDeviceStartFixture)


class TriggerStartFixture(Fixture):
    """ Dependencies: ControllerDeviceStartedFixture
    Make a trigger and ask the plugin to start processing it. Also
    mock two "other event" messages, one that matches the trigger and
    one that doesn't.
    """
    def setUp(self, tc):
        tc.trigger = Mock()
        tc.trigger.id = 1
        tc.trigger.pluginTypeId = "batteryOK"
        tc.trigger.pluginProps = {"controllerId": unicode(tc.dev.id)}
        tc.plugin.triggerStartProcessing(tc.trigger)

        # a message matching the trigger
        tc.event_msg = JomnilinkII_OtherEventNotifications_for_test(
            [0x0307])
        # and one that doesn't
        tc.mismatch_msg = JomnilinkII_OtherEventNotifications_for_test(
            [0x0303, 0x0406])

TriggerStartedFixture = CompositeFixture(ControllerDeviceStartedFixture,
                                         TriggerStartFixture)


class ControllerTestCase(TestCaseWithFixtures):
    """ Test cases that require a started plugin, but no controller devices """
    def setUp(self):
        TestCaseWithFixtures.setUp(self)
        self.useFixture(PluginStartedFixture)
        self.useFixture(ConnectionValuesFixture)

    def test_GetDeviceList_ReturnsController(self):
        values = self.plugin.makeConnection(dict(self.values), [])

        result = self.plugin.getDeviceGroupList(None, values, [])

        self.assertTrue(("omniControllerDevice", "Controller") in result)

    def test_CreateDevices_CreatesOnlyOneController(self):
        values = self.plugin.makeConnection(dict(self.values), [])
        values["deviceGroupList"] = ["omniControllerDevice"]

        self.plugin.createDevices(values,
                                  [dev.id for dev in indigo.devices.values()])
        self.assertEqual(
            len(set([dev for dev in indigo.devices.values()
                     if dev.deviceTypeId == "omniControllerDevice"])), 1)

        self.plugin.createDevices(values,
                                  [dev.id for dev in indigo.devices.values()])
        self.assertEqual(
            len(set([dev for dev in indigo.devices.values()
                     if dev.deviceTypeId == "omniControllerDevice"])), 1)

    def test_DeviceStartComm_Fails_OnNetworkError(self):
        self.connection_mock.reqSystemInformation = Mock(
            side_effect=self.plugin_module.extensions.ConnectionError)
        dev = ControllerDeviceFixture.create_controller_device(self)

        self.plugin.deviceStartComm(dev)

        self.assertTrue(dev.error_state is not None)
        self.assertTrue(self.plugin.errorLog.called)
        self.plugin.errorLog.reset_mock()

    def test_DeviceStopComm_Succeeds(self):
        self.connection_mock.reqSystemInformation = Mock(
            return_value=JomnilinkII_SystemInformation_for_test(37, 3, 0, 254,
                                                                ""))
        self.connection_mock.reqSystemStatus = Mock(
            return_value=JomnilinkII_SystemStatus_for_test(0))
        self.connection_mock.reqSystemTroubles = Mock(
            return_value=JomnilinkII_SystemTroubles_for_test([5, 6]))
        dev = ControllerDeviceFixture.create_controller_device(self)
        self.plugin.deviceStartComm(dev)
        self.assertFalse(self.plugin.errorLog.called)
        self.assertEqual(dev.states["connected"], True)
        self.assertEqual(dev.states["model"], "HAI Lumina Pro")
        self.assertEqual(dev.states["firmwareVersion"], "3.0X2")
        troubles = {"freezeTrouble": False,
                    "batteryLowTrouble": False,
                    "ACPowerTrouble": False,
                    "phoneLineTrouble": False,
                    "digitalCommunicatorTrouble": True,
                    "fuseTrouble": True}
        for t, val in troubles.items():
            self.assertEqual(dev.states[t], val)

        self.plugin.deviceStopComm(dev)

    def test_WriteControllerInfoToLog_Succeeds(self):
        mock_capacities = Mock()
        mock_capacities.getCapacity.return_value = 2
        mock_troubles = Mock()
        mock_troubles.getTroubles.return_value = ["trouble"]
        mock_features = Mock()
        mock_features.getFeatures.return_value = ["features"]
        mock_statuses = Mock()
        mock_statuses.getStatuses.return_value = [Mock()]
        mock_properties = self.create_reqObjProperties_Mock()

        for cm in self.connection_mocks:
            cm.reqObjectTypeCapacities.return_value = mock_capacities
            cm.reqSystemTroubles.return_value = mock_troubles
            cm.reqSystemFeatures.return_value = mock_features
            cm.reqObjectStatus.return_value = mock_statuses
            cm.reqObjectProperties = mock_properties

        self.plugin.makeConnection(self.values, [])
        self.plugin.makeConnection(self.values2, [])
        self.plugin.writeControllerInfoToLog()

    def create_reqObjProperties_Mock(self):
        self.jomnilinkII_mock.Message.MESG_TYPE_OBJ_PROP = 0x21

        class locals:
            objs = [JomnilinkII_ObjectProperties_for_test(0, 1, "Thing 1",
                                                          0x21),
                    JomnilinkII_ObjectProperties_for_test(0, 2, "Thing 2",
                                                          0x21),
                    JomnilinkII_ObjectProperties_for_test(0, 0, "", 0)]
            index = 0

        def looper(a, b, c, d, e, f):
            retval = locals.objs[locals.index % len(locals.objs)]
            locals.index += 1
            return retval

        return Mock(side_effect=looper)

    def test_WriteControllerInfoToLog_Handles_NetworkError(self):
        self.connection_mock.reqSystemInformation = Mock(
            side_effect=self.plugin_module.extensions.ConnectionError)
        self.plugin.makeConnection(self.values, [])
        self.assertFalse(self.plugin.errorLog.called)

        self.plugin.writeControllerInfoToLog()

        self.assertTrue(self.plugin.errorLog.called)
        self.plugin.errorLog.reset_mock()

    def test_WriteControllerInfoToLog_Handles_FailedStartup(self):
        self.plugin.makeConnection(self.values, [])
        self.connection_mock.connected.return_value = False
        self.plugin_module.indigo.server.log.reset_mock()

        self.plugin.writeControllerInfoToLog()

        self.assertTrue(self.plugin_module.indigo.server.log.call_count == 1)
        args, kwargs = self.plugin_module.indigo.server.log.call_args
        self.assertTrue("is not connected" in args[0])


class ControllerDeviceTestCase(TestCaseWithFixtures):
    """ Test cases that need the connections mocked and a device already
    created """
    def setUp(self):
        TestCaseWithFixtures.setUp(self)
        self.useFixture(PluginStartedFixture)
        self.useFixture(ConnectionValuesFixture)
        self.useFixture(ControllerDeviceFixture)

    def test_DeviceStartComm_Succeeds(self):
        self.plugin.deviceStartComm(self.dev)

        self.assertEqual(self.dev.states["connected"], True)
        self.assertEqual(self.dev.states["model"], "HAI Omni IIe")
        self.assertEqual(self.dev.states["firmwareVersion"], "2.16b")
        self.assertEqual(self.dev.states["batteryReading"], 200)
        troubles = {"freezeTrouble": True,
                    "batteryLowTrouble": True,
                    "ACPowerTrouble": True,
                    "phoneLineTrouble": True,
                    "digitalCommunicatorTrouble": False,
                    "fuseTrouble": False}
        for t, val in troubles.items():
            self.assertEqual(self.dev.states[t], val)

    def test_DeviceStartComm_Updates_OldDevices(self):
        del self.dev.pluginProps["deviceVersion"]

        with patch.object(self.dev, "stateListOrDisplayStateIdChanged") as m:
            self.plugin.deviceStartComm(self.dev)
            self.assertTrue(m.called)

        self.assertTrue("deviceVersion" in self.dev.pluginProps)

    def test_DisconnectNotification_SetsErrorState_OfCorrectController(self):
        dev2 = ControllerDeviceFixture.create_controller_device(self,
                                                                self.values2)
        self.plugin.deviceStartComm(self.dev)
        self.plugin.deviceStartComm(dev2)
        for listener in self.disconnect_listeners[1]:
            listener.notConnectedEvent(Mock())
        self.assertTrue(dev2.error_state is not None)


class ControllerDeviceStartedTestCase(TestCaseWithFixtures):
    """ Test cases that need the connections mocked and a device already
    created and started """
    def setUp(self):
        TestCaseWithFixtures.setUp(self)
        self.useFixture(ControllerDeviceStartedFixture)

    def test_ReconnectNotification_Clears_DeviceErrorState(self):
        self.assertFalse(self.dev.states["digitalCommunicatorTrouble"])

        self.connection_mocks[0].connected.return_value = False
        for listener in self.disconnect_listeners[0]:
            listener.notConnectedEvent(Mock())

        self.assertTrue(self.dev.error_state is not None)
        self.connection_mocks[1].reqSystemTroubles = Mock(
            return_value=JomnilinkII_SystemTroubles_for_test([5, 6]))

        self.plugin.update()  # this should get the second connection object
        self.assertTrue(self.dev.error_state is None)
        self.assertTrue(self.dev.states["digitalCommunicatorTrouble"])

    def test_ValidateActionConfigUI_Catches_ObviousErrors(self):
        values = {}
        self.plugin.getActionConfigUiValues(values, "checkSecurityCode",
                                            self.dev.id)

        with patch.object(self.plugin_module.indigo.PluginBase, "substitute",
                          return_value=(True, "")) as sub:

            values["code"] = "%%blahblah"
            values["area"] = "%%blahblah"
            tup = self.plugin.validateActionConfigUi(values,
                                                     "checkSecurityCode",
                                                     1)
            self.assertTrue(tup[0])
            self.assertFalse(tup[2])
            self.assertEqual(sub.call_count, 2)

        test_values = [("123A", "hello"), ("", ""), ("0", "0")]
        for code, area in test_values:
            values["code"] = code
            values["area"] = area
            tup = self.plugin.validateActionConfigUi(values,
                                                     "checkSecurityCode", 1)
            self.assertFalse(tup[0])
            self.assertTrue("code" in tup[2])
            self.assertTrue("area" in tup[2])

    def test_CheckSecurityCode_UpdatesDeviceStates_OnValidCode(self):
        mock_scv = JomnilinkII_SecurityCodeValidation_for_test(16, 2)
        self.connection_mock.reqSecurityCodeValidation = Mock(
            return_value=mock_scv)

        action = Mock()
        action.deviceId = self.dev.id
        action.props = {"code": "9876", "area": "1", "actionVersion": _VERSION}

        self.plugin.checkSecurityCode(action)

        self.connection_mock.reqSecurityCodeValidation.assert_called_with(
            1, 9, 8, 7, 6)
        self.assertEqual(self.dev.states["lastCheckedCode"],
                         action.props["code"])
        self.assertEqual(self.dev.states["lastCheckedCodeArea"],
                         action.props["area"])
        self.assertEqual(self.dev.states["lastCheckedCodeAuthority"],
                         "Manager")
        self.assertEqual(self.dev.states["lastCheckedCodeUser"], 16)
        self.assertFalse(self.dev.states["lastCheckedCodeDuress"])

    def test_CheckSecurityCode_HandlesNetworkError(self):
        self.connection_mock.reqSecurityCodeValidation = Mock(
            side_effect=self.plugin_module.py4j.protocol.Py4JError)

        action = Mock()
        action.deviceId = self.dev.id
        action.props = {"code": "9876", "area": "1", "actionVersion": _VERSION}
        self.assertFalse(self.plugin.errorLog.called)

        self.plugin.checkSecurityCode(action)

        self.assertTrue(self.plugin.errorLog.called)
        self.plugin.errorLog.reset_mock()

        self.assertEqual(self.dev.states["lastCheckedCode"],
                         action.props["code"])
        self.assertEqual(self.dev.states["lastCheckedCodeArea"],
                         action.props["area"])
        self.assertEqual(self.dev.states["lastCheckedCodeAuthority"], "Error")
        self.assertEqual(self.dev.states["lastCheckedCodeUser"], "N/A")
        self.assertFalse(self.dev.states["lastCheckedCodeDuress"])

    def test_TriggerStartProcessing_Handles_UnconfiguredTrigger(self):
        trigger = Mock()
        trigger.id = 1
        trigger.pluginTypeId = "batteryLow"
        trigger.pluginProps = {}
        self.plugin.triggerStartProcessing(trigger)
        self.assertTrue(self.plugin.errorLog.called)
        self.plugin.errorLog.reset_mock()

    def test_TriggerProcessing_Succeeds_WithValidTrigger(self):
        trigger = Mock()
        trigger.id = 1
        trigger.pluginTypeId = "batteryLow"
        trigger.pluginProps = {"controllerId": unicode(self.dev.id)}
        self.plugin.triggerStartProcessing(trigger)
        self.plugin.triggerStopProcessing(trigger)


class TriggerTestCase(TestCaseWithFixtures):
    def setUp(self):
        TestCaseWithFixtures.setUp(self)
        self.useFixture(TriggerStartedFixture)

    def test_OtherEventNotification_Executes_Trigger(self):
        for listener in self.notify_listeners[0]:
            listener.otherEventNotification(self.event_msg)

        self.assertTrue(self.plugin_module.indigo.trigger.execute.called)

    def test_OtherEventNotification_UpdatesDeviceState(self):
        self.connection_mock.reqSystemTroubles = Mock(
            return_value=JomnilinkII_SystemTroubles_for_test([]))

        for listener in self.notify_listeners[0]:
            listener.otherEventNotification(self.event_msg)

        self.assertFalse(self.dev.states["batteryLowTrouble"])

    def test_OtherEventNotification_Ignores_UnknownMessage(self):
        for listener in self.notify_listeners[0]:
            listener.otherEventNotification(self.mismatch_msg)

        self.assertFalse(self.plugin_module.indigo.trigger.execute.called)

    def test_OtherEventNotification_Ignores_MessageForStoppedDevice(self):
        self.plugin.deviceStopComm(self.dev)

        for listener in self.notify_listeners[0]:
            listener.otherEventNotification(self.event_msg)

        self.assertFalse(self.plugin_module.indigo.trigger.execute.called)


if __name__ == "__main__":
    unittest.main()

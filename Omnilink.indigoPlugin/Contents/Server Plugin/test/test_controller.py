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

from mock import Mock
import pytest

import fixtures.jomnilinkII as jomni_mimic
from fixtures.omni import omni1_system_messages_asserts
from fixtures.omni import omni2_system_messages_asserts


@pytest.fixture
def controller_device(indigo, plugin, device_factory_fields):
    values = plugin.makeConnection(device_factory_fields, [])
    values["deviceGroupList"] = ["omniControllerDevice"]
    plugin.createDevices(
        values,
        [dev.id for dev in indigo.devices.iter()
         if dev.pluginProps["ipAddress"] == values["ipAddress"]])

    dev = [dev for dev in indigo.devices.iter()
           if (dev.deviceTypeId == "omniControllerDevice" and
               dev.pluginProps["ipAddress"] == values["ipAddress"])]
    assert len(dev) == 1
    return dev[0]


@pytest.fixture
def started_controller_device(plugin, controller_device):
    plugin.deviceStartComm(controller_device)
    return controller_device


@pytest.fixture
def second_controller_device(indigo, plugin,
                             device_factory_fields_2,
                             controller_device):
    values = plugin.makeConnection(device_factory_fields_2, [])
    values["deviceGroupList"] = ["omniControllerDevice"]
    plugin.createDevices(
        values,
        [dev.id for dev in indigo.devices.iter()
         if dev.pluginProps["ipAddress"] == values["ipAddress"]])

    dev = [dev for dev in indigo.devices.iter()
           if (dev.deviceTypeId == "omniControllerDevice" and
               dev.pluginProps["ipAddress"] == values["ipAddress"])]
    assert len(dev) == 1
    return dev[0]


@pytest.fixture
def trigger(plugin, started_controller_device):
    """ Create and start a controller trigger """
    dev = started_controller_device

    trigger = Mock()
    trigger.id = 1
    trigger.pluginTypeId = "batteryOK"
    trigger.pluginProps = {"controllerId": unicode(dev.id)}
    plugin.triggerStartProcessing(trigger)
    return trigger


@pytest.fixture
def trigger_event():
    """ return a message matching the trigger """
    event_msg = jomni_mimic.OtherEventNotifications([0x0307])
    return event_msg


@pytest.fixture
def trigger_non_event():
    """ return a message that doesn't match the trigger """
    mismatch_msg = jomni_mimic.OtherEventNotifications(
        [0x0303, 0x0406])
    return mismatch_msg


def test_get_device_list_returns_controller(plugin, device_factory_fields):
    values = plugin.makeConnection(device_factory_fields, [])

    result = plugin.getDeviceGroupList(None, values, [])

    assert ("omniControllerDevice", "Controller") in result


def test_create_devices_creates_only_one_controller(indigo, plugin,
                                                    device_factory_fields):
    values = plugin.makeConnection(device_factory_fields, [])
    values["deviceGroupList"] = ["omniControllerDevice"]

    plugin.createDevices(values,
                         [dev.id for dev in indigo.devices.iter()])
    assert len([dev for dev in indigo.devices.iter()
                if dev.deviceTypeId == "omniControllerDevice"]) == 1

    plugin.createDevices(values,
                         [dev.id for dev in indigo.devices.iter()])
    assert len([dev for dev in indigo.devices.iter()
                if dev.deviceTypeId == "omniControllerDevice"]) == 1


def create_reqObjProperties(jomnilinkII):
    mtype = jomnilinkII.Message.MESG_TYPE_OBJ_PROP = 0x21

    class locals:
        objs = [jomni_mimic.ObjectProperties(0, 1, "Thing 1", mtype),
                jomni_mimic.ObjectProperties(0, 2, "Thing 2", mtype),
                jomni_mimic.ObjectProperties(0, 0, "", 0)]
        index = 0

    def looper(a, b, c, d, e, f):
        retval = locals.objs[locals.index % len(locals.objs)]
        locals.index += 1
        return retval

    return looper


def create_uploadEventLogData(jomnilinkII):
    mtype = jomnilinkII.Message.MESG_TYPE_EVENT_LOG_DATA = 99

    class locals:
        objs = [
            jomni_mimic.EventLogData(
                mtype, 0, True, 3, 28, 10, 30, 135, 8, 0),
            jomni_mimic.EventLogData(
                mtype, 0, True, 3, 28, 10, 30, 4, 254, 4),
            jomni_mimic.EventLogData(
                mtype, 0, False, 3, 28, 10, 30, 138, 0, 1),
            jomni_mimic.EventLogData(
                0, 0, False, 3, 28, 10, 30, 0, 0, 0)]
        index = 0

    def looper(a, b):
        retval = locals.objs[locals.index % len(locals.objs)]
        locals.index += 1
        return retval

    return looper


def test_write_controller_info_to_log_succeeds(plugin, omnis, jomnilinkII,
                                               device_factory_fields,
                                               device_factory_fields_2):
    mock_capacities = Mock()
    mock_capacities.getCapacity.return_value = 2
    mock_troubles = Mock()
    mock_troubles.getTroubles.return_value = ["trouble"]
    mock_features = Mock()
    mock_features.getFeatures.return_value = ["features"]
    mock_statuses = Mock()
    mock_statuses.getStatuses.return_value = [Mock()]
    mock_properties = create_reqObjProperties(jomnilinkII)
    mock_log = create_uploadEventLogData(jomnilinkII)

    for omni in omnis:
        omni.reqObjectTypeCapacities.return_value = mock_capacities
        omni.reqSystemTroubles.return_value = mock_troubles
        omni.reqSystemFeatures.return_value = mock_features
        omni.reqObjectStatus.return_value = mock_statuses
        omni.reqObjectProperties = mock_properties
        omni.uploadEventLogData = mock_log

    plugin.makeConnection(device_factory_fields, [])
    plugin.makeConnection(device_factory_fields_2, [])
    plugin.writeControllerInfoToLog()


def test_write_controller_info_to_log_handles_network_error(
        plugin, omni1, plugin_module, device_factory_fields):
    omni1.reqSystemInformation.side_effect = plugin_module.ConnectionError
    plugin.makeConnection(device_factory_fields, [])
    assert not plugin.errorLog.called

    plugin.writeControllerInfoToLog()

    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_write_controller_info_to_log_handles_failed_startup(
        indigo, plugin, omni1, device_factory_fields):
    plugin.makeConnection(device_factory_fields, [])
    omni1.connected.return_value = False
    indigo.server.log.reset_mock()

    plugin.writeControllerInfoToLog()

    indigo.server.log.call_count == 1
    args, kwargs = indigo.server.log.call_args
    assert "is not connected" in args[0]


def test_device_start_comm_fails_on_network_error(plugin_module, plugin,
                                                  controller_device, omni1):
    omni1.reqSystemInformation.side_effect = plugin_module.ConnectionError

    plugin.deviceStartComm(controller_device)

    assert controller_device.error_state is not None
    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_device_start_comm_succeeds(plugin, controller_device,
                                    second_controller_device):
    plugin.deviceStartComm(controller_device)
    omni1_system_messages_asserts(controller_device)

    plugin.deviceStartComm(second_controller_device)
    omni2_system_messages_asserts(second_controller_device)


def test_device_start_comm_updates_old_devices(plugin, controller_device,
                                               monkeypatch):
    del controller_device.pluginProps["deviceVersion"]
    m = Mock()
    monkeypatch.setattr(controller_device,
                        "stateListOrDisplayStateIdChanged", m)
    plugin.deviceStartComm(controller_device)
    assert m.called
    assert "deviceVersion" in controller_device.pluginProps


def test_device_stop_comm_succeeds(plugin, controller_device):
    plugin.deviceStopComm(controller_device)


def test_disconnect_notification_sets_error_state_of_correct_controller(
        plugin, started_controller_device, second_controller_device, omni2):

    plugin.deviceStartComm(second_controller_device)
    omni2._disconnect("notConnectedEvent", Mock())

    assert started_controller_device.error_state is None
    assert second_controller_device.error_state is not None


def test_reconnect_notification_clears_device_error_state(
        plugin, started_controller_device, omni1, omni2):

    omni1_system_messages_asserts(started_controller_device)
    omni1.connected.return_value = False
    omni1._disconnect("notConnectedEvent", Mock())

    assert started_controller_device.error_state is not None

    # plugin should now try to reconnect, and jomnilinkII
    # will give it omni2
    plugin.update()

    assert started_controller_device.error_state is None
    omni2_system_messages_asserts(started_controller_device)


def test_validate_action_config_ui_uses_substitute_check(
        plugin, controller_device, monkeypatch, indigo):
    values = {}
    plugin.getActionConfigUiValues(values, "checkSecurityCode",
                                   controller_device.id)

    sub = Mock(return_value=(True, ""))
    monkeypatch.setattr(indigo.PluginBase, "substitute", sub)
    values["code"] = "%%blahblah"
    values["area"] = "%%blahblah"
    tup = plugin.validateActionConfigUi(values, "checkSecurityCode", 1)

    assert tup[0]
    assert not tup[2]
    assert sub.call_count == 2


def test_validate_action_config_ui_catches_obvious_errors(
        plugin, controller_device):
    values = {}
    plugin.getActionConfigUiValues(values, "checkSecurityCode",
                                   controller_device.id)
    test_values = [("123A", "hello"), ("", ""), ("0", "0")]
    for code, area in test_values:
        values["code"] = code
        values["area"] = area
        tup = plugin.validateActionConfigUi(values, "checkSecurityCode", 1)
        assert not tup[0]
        assert "code" in tup[2]
        assert "area" in tup[2]


def test_check_security_code_updates_device_states_on_valid_code(
        plugin, started_controller_device, omni1, version):
    dev = started_controller_device
    mock_scv = jomni_mimic.SecurityCodeValidation(16, 2)
    omni1.reqSecurityCodeValidation = Mock(return_value=mock_scv)

    action = Mock()
    action.deviceId = dev.id
    action.props = {"code": "9876", "area": "1", "actionVersion": version}

    plugin.checkSecurityCode(action)

    omni1.reqSecurityCodeValidation.assert_called_with(1, 9, 8, 7, 6)
    assert dev.states["lastCheckedCode"] == action.props["code"]
    assert dev.states["lastCheckedCodeArea"] == action.props["area"]
    assert dev.states["lastCheckedCodeAuthority"] == "Manager"
    assert dev.states["lastCheckedCodeUser"] == 16
    assert not dev.states["lastCheckedCodeDuress"]


def test_check_security_code_handles_network_error(
        plugin, started_controller_device, omni1, py4j, version):
    dev = started_controller_device
    omni1.reqSecurityCodeValidation = Mock(
        side_effect=py4j.protocol.Py4JError)

    action = Mock()
    action.deviceId = dev.id
    action.props = {"code": "9876", "area": "1", "actionVersion": version}
    assert not plugin.errorLog.called

    plugin.checkSecurityCode(action)

    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()

    assert dev.states["lastCheckedCode"] == action.props["code"]
    assert dev.states["lastCheckedCodeArea"] == action.props["area"]
    assert dev.states["lastCheckedCodeAuthority"] == "Error"
    assert dev.states["lastCheckedCodeUser"] == "N/A"
    assert not dev.states["lastCheckedCodeDuress"]


def test_trigger_start_processing_handles_unconfigured_trigger(
        plugin, started_controller_device):
    trigger = Mock()
    trigger.id = 1
    trigger.pluginTypeId = "batteryLow"
    trigger.pluginProps = {}
    plugin.triggerStartProcessing(trigger)
    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_trigger_processing_succeeds_with_valid_trigger(
        plugin, trigger):
    plugin.triggerStopProcessing(trigger)


def test_other_event_notification_executes_trigger(
        plugin, omni1, indigo, trigger, trigger_event):
    omni1._notify("otherEventNotification", trigger_event),
    assert indigo.trigger.execute.called


def test_other_event_notification_updates_device_state(
        plugin, started_controller_device, trigger_event, omni1):
    omni1.reqSystemTroubles.return_value = jomni_mimic.SystemTroubles([])
    assert started_controller_device.states["batteryLowTrouble"]

    omni1._notify("otherEventNotification", trigger_event)

    assert not started_controller_device.states["batteryLowTrouble"]


def test_other_event_notification_ignores_unknown_message(
        plugin, omni1, indigo, started_controller_device, trigger,
        trigger_non_event):

    omni1._notify("otherEventNotification", trigger_non_event)

    assert not indigo.trigger.execute.called


def test_other_event_notification_ignores_message_for_stopped_device(
        plugin, omni1, indigo, started_controller_device, trigger,
        trigger_event):
    plugin.deviceStopComm(started_controller_device)

    omni1._notify("otherEventNotification", trigger_event)

    assert not indigo.trigger.execute.called

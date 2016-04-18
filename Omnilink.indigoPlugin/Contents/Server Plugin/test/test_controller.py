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
from time import sleep

from mock import Mock
import pytest

import fixtures.helpers as helpers
import fixtures.jomnilinkII as jomni_mimic
from fixtures.omni import omni1_system_messages_asserts
from fixtures.omni import omni2_system_messages_asserts


@pytest.fixture
def controller_device(indigo, plugin, device_factory_fields,
                      device_connection_props):
    values = plugin.makeConnection(device_factory_fields, [])
    values["deviceGroupList"] = ["omniControllerDevice"]
    plugin.createDevices(
        values,
        [dev.id for dev in indigo.devices.iter()
         if dev.pluginProps["url"] == device_connection_props["url"]])

    dev = [dev for dev in indigo.devices.iter()
           if (dev.deviceTypeId == "omniControllerDevice" and
               dev.pluginProps["url"] == device_connection_props["url"])]
    assert len(dev) == 1
    return dev[0]


@pytest.fixture
def started_controller_device(plugin, controller_device):
    plugin.deviceStartComm(controller_device)
    return controller_device


@pytest.fixture
def second_controller_device(indigo, plugin,
                             device_factory_fields_2,
                             device_connection_props_2,
                             controller_device):
    values = plugin.makeConnection(device_factory_fields_2, [])
    values["deviceGroupList"] = ["omniControllerDevice"]
    plugin.createDevices(
        values,
        [dev.id for dev in indigo.devices.iter()
         if dev.pluginProps["url"] == device_connection_props_2["url"]])

    dev = [dev for dev in indigo.devices.iter()
           if (dev.deviceTypeId == "omniControllerDevice" and
               dev.pluginProps["url"] == device_connection_props_2["url"])]
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
    helpers.run_concurrent_thread(plugin, 1)

    assert started_controller_device.error_state is None
    assert second_controller_device.error_state is not None

    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_reconnect_notification_clears_device_error_state(
        plugin, started_controller_device, omni1, omni2,
        patched_datetime):

    # make sure controller device is running and updated
    omni1_system_messages_asserts(started_controller_device)
    helpers.run_concurrent_thread(plugin, 1)

    # make the mock jomnilinkII.Connection disconnect
    omni1.connected.return_value = False
    omni1._disconnect("notConnectedEvent", Mock())

    # and let the disconnect message get processed
    helpers.run_concurrent_thread(plugin, 1)

    # now the device should be in the error state
    assert started_controller_device.error_state is not None
    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()

    # let the disconnect message get processed
    patched_datetime.fast_forward(minutes=2)

    # allow time for the thread to run by using the real sleep,
    # not the patched one in the plugin
    sleep(0.1)

    # let the reconnect message get processed
    helpers.run_concurrent_thread(plugin, 1)

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
    omni1._notify("otherEventNotification", trigger_event)
    helpers.run_concurrent_thread(plugin, 1)
    assert indigo.trigger.execute.called


def test_other_event_notification_updates_device_state(
        plugin, started_controller_device, trigger_event, omni1):
    omni1.reqSystemTroubles.return_value = jomni_mimic.SystemTroubles([])
    assert started_controller_device.states["batteryLowTrouble"]

    omni1._notify("otherEventNotification", trigger_event)
    helpers.run_concurrent_thread(plugin, 1)

    assert not started_controller_device.states["batteryLowTrouble"]


def test_other_event_notification_ignores_unknown_message(
        plugin, omni1, indigo, started_controller_device, trigger,
        trigger_non_event):

    omni1._notify("otherEventNotification", trigger_non_event)
    helpers.run_concurrent_thread(plugin, 1)

    assert not indigo.trigger.execute.called


def test_other_event_notification_ignores_message_for_stopped_device(
        plugin, omni1, indigo, started_controller_device, trigger,
        trigger_event):
    plugin.deviceStopComm(started_controller_device)

    omni1._notify("otherEventNotification", trigger_event)
    helpers.run_concurrent_thread(plugin, 1)

    assert not indigo.trigger.execute.called


def test_generate_keypad_list_checks_keypad_count(
        plugin, omni1, started_controller_device, jomnilinkII):

    omni1.reqObjectTypeCapacities.return_value.getCapacity.return_value = 8

    values = {}
    plugin.getActionConfigUiValues(values, "checkSecurityCode",
                                   started_controller_device.id)
    tups = plugin.generateConsoleList(None, values,
                                      "enableConsoleBeeper",
                                      started_controller_device.id)
    assert omni1.reqObjectTypeCapacities.called_with(
        jomnilinkII.Message.OBJ_TYPE_CONSOLE)

    assert len(tups) == 9


def test_enable_disable_keypad_beeper_sends_command(
        plugin, indigo, omni1, started_controller_device, jomnilinkII):
    action = Mock()
    action.deviceId = started_controller_device.id
    action.props = {"consoleNumber": "3"}
    action.pluginTypeId = "enableConsoleBeeper"

    plugin.enableConsoleBeeper(action)

    CM = jomnilinkII.MessageTypes.CommandMessage
    assert omni1.controllerCommand.called_with(
        CM.CMD_CONSOLE_ENABLE_DISABLE_BEEPER, 1, 3)

    action.props["consoleNumber"] = "0"
    action.pluginTypeId = "disableConsoleBeeper"
    plugin.disableConsoleBeeper(action)

    assert omni1.controllerCommand.called_with(
        CM.CMD_CONSOLE_ENABLE_DISABLE_BEEPER, 0, 0)


def test_enable_disable_keypad_handles_network_error(
        plugin, plugin_module, indigo, omni1, started_controller_device):
    action = Mock()
    action.deviceId = started_controller_device.id
    action.props = {"consoleNumber": "3"}
    action.pluginTypeId = "enableConsoleBeeper"

    omni1.connected.side_effect = plugin_module.ConnectionError
    plugin.enableConsoleBeeper(action)

    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_enable_disable_keypad_beeper_handles_unconfigured_action(
        plugin, started_controller_device):
    action = Mock()
    action.deviceId = started_controller_device.id
    action.props = {}
    action.pluginTypeId = "enableConsoleBeeper"

    plugin.enableConsoleBeeper(action)

    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_send_keypad_beep_sends_command(
        plugin, indigo, omni1, started_controller_device, jomnilinkII):
    action = Mock()
    action.deviceId = started_controller_device.id
    action.props = {"consoleNumber": "0",
                    "beepCommand": "beepOff"}
    action.pluginTypeId = "sendBeepCommand"
    CM = jomnilinkII.MessageTypes.CommandMessage

    plugin.sendBeepCommand(action)

    assert omni1.controllerCommand.called_with(CM.CMD_CONSOLE_BEEP, 0, 0)

    action.props["consoleNumber"] = "4"
    action.props["beepCommand"] = "beep5"
    action.pluginTypeId = "sendBeepCommand"
    plugin.sendBeepCommand(action)

    assert omni1.controllerCommand.called_with(
        CM.CMD_CONSOLE_ENABLE_DISABLE_BEEPER, 6, 1)


def test_send_keypad_beep_handles_network_error(
        plugin, py4j, omni1, started_controller_device):
    action = Mock()
    action.deviceId = started_controller_device.id
    action.props = {"consoleNumber": "0",
                    "beepCommand": "beepOn"}
    action.pluginTypeId = "sendBeepCommand"

    omni1.controllerCommand.side_effect = py4j.protocol.Py4JError

    plugin.sendBeepCommand(action)

    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_send_keypad_beep_error_checks_when_scripted(
        plugin, started_controller_device):
    action = Mock()
    action.deviceId = started_controller_device.id
    action.props = {"consoleNumber": "0",
                    "beepCommand": "doTheHokeyPokey"}
    action.pluginTypeId = "sendBeepCommand"

    plugin.sendBeepCommand(action)
    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_send_keypad_beep_handles_unconfigured_action(
        plugin, started_controller_device):
    action = Mock()
    action.deviceId = started_controller_device.id
    action.props = {}
    action.pluginTypeId = "sendBeepCommand"

    plugin.sendBeepCommand(action)

    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()

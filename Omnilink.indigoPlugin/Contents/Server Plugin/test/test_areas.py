#! /usr/bin/env python
# Unit Tests for areas extension to Omnilink Plugin for Indigo Server
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

import fixtures.jomnilinkII as jomni_mimic
import fixtures.helpers as helpers


def create_area_devices(plugin, indigo, values, device_connection_props):
    values = plugin.makeConnection(values, [])
    values["deviceGroupList"] = ["omniAreaDevice"]
    plugin.createDevices(
        values,
        [dev.id for dev in indigo.devices.iter()
         if dev.pluginProps["address"] == device_connection_props["address"]])
    return [dev for dev in indigo.devices.iter()
            if (dev.deviceTypeId == "omniAreaDevice" and
                dev.pluginProps["address"] ==
                device_connection_props["address"])]


@pytest.fixture
def area_devices(plugin, indigo, device_factory_fields,
                 device_connection_props):
    """ Ask the plugin to create one batch of area devices, return a list
    of them. """
    return create_area_devices(plugin, indigo, device_factory_fields,
                               device_connection_props)


@pytest.fixture
def area_devices_2(plugin, indigo, device_factory_fields_2, area_devices,
                   device_connection_props_2):
    """ Ask the plugin to create area devices on omni2 """
    return create_area_devices(plugin, indigo, device_factory_fields_2,
                               device_connection_props_2)


def test_get_device_list_returns_area(plugin, device_factory_fields, omni1):
    plugin.makeConnection(device_factory_fields, [])
    result = plugin.getDeviceGroupList(None, device_factory_fields, [])
    assert omni1.reqObjectProperties.called
    assert ("omniAreaDevice", "Area") in result


def test_get_device_list_returns_empty_list_on_connection_error(
        plugin, plugin_module, device_factory_fields, omni1):
    plugin.makeConnection(device_factory_fields, [])

    ConnectionError = plugin_module.ConnectionError
    omni1.reqObjectProperties.side_effect = ConnectionError

    result = plugin.getDeviceGroupList(None, device_factory_fields, [])

    assert ("omniAreaDevice", "Area") not in result
    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_create_devices_creates_device_for_enabled_areas(
        indigo, plugin, device_factory_fields, area_devices):
    assert (len([dev for dev in indigo.devices.iter()
                 if dev.deviceTypeId == "omniAreaDevice"]) == 2)

    plugin.createDevices(device_factory_fields,
                         [dev.id for dev in indigo.devices.iter()])

    assert (len([dev for dev in indigo.devices.iter()
                 if dev.deviceTypeId == "omniAreaDevice"]) == 2)


def test_device_start_comm_succeeds_on_valid_input(
        indigo, plugin, area_devices,
        req_object_props_area_states):

    for dev in area_devices:
        plugin.deviceStartComm(dev)

    for dev in area_devices:
        assert dev.errorState is None
        right_answers = req_object_props_area_states[dev.name]
        for k, v in right_answers.items():
            assert dev.states[k] == v


def test_device_start_comm_sets_errorState_on_connection_error(
        indigo, py4j, plugin, omni1, area_devices):
    dev = indigo.devices["First Area"]
    omni1.reqObjectStatus.side_effect = py4j.protocol.Py4JError

    plugin.deviceStartComm(dev)
    assert dev.errorState is not None


def test_remove_devices_removes_area_devices(plugin, indigo, area_devices,
                                             device_factory_fields):
    dev_ids = [dev.id for dev in area_devices]
    plugin.removeDevices(device_factory_fields, dev_ids)
    devs = [dev for dev in indigo.devices
            if dev.deviceTypeId == "omniAreaDevice"]
    assert not devs


def test_notification_changes_device_state(plugin, indigo, area_devices,
                                           jomnilinkII, omni1):
    dev = indigo.devices["Area 2"]
    plugin.deviceStartComm(dev)
    assert dev.states["mode"] == "Off"
    assert not plugin.errorLog.called

    status_msg = jomni_mimic.ObjectStatus(
        jomnilinkII.Message.OBJ_TYPE_AREA,
        [jomni_mimic.AreaStatus(2, 2, 0, 0, 0)])

    omni1._notify("objectStausNotification", status_msg)
    helpers.run_concurrent_thread(plugin, 1)

    assert dev.states["mode"] == "Night"
    assert dev.errorState is None


def test_notification_ignores_non_area_notifications(plugin, indigo, omni1,
                                                     area_devices):
    status_msg = jomni_mimic.ObjectStatus(Mock(),
                                          [jomni_mimic.UnitStatus(1, 1, 100)])
    dev = indigo.devices["First Area"]
    plugin.deviceStartComm(dev)

    omni1._notify("objectStausNotification", status_msg)
    helpers.run_concurrent_thread(plugin, 1)

    assert dev.states["mode"] == "Off"


def test_disconnect_notification_sets_errorState_of_correct_area_device(
        plugin, indigo, area_devices, device_factory_fields,
        omni2, area_devices_2, device_factory_fields_2):

    assert len(area_devices_2) == 2

    for dev in area_devices + area_devices_2:
        plugin.deviceStartComm(dev)

    omni2._disconnect("notConnectedEvent", Mock())

    helpers.run_concurrent_thread(plugin, 1)

    for dev in area_devices:
        assert dev.errorState is None
    for dev in area_devices_2:
        assert dev.errorState is not None

    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_reconnect_notification_clears_device_errorState(
        plugin, indigo, area_devices, omni1, patched_datetime):
    for dev in area_devices:
        plugin.deviceStartComm(dev)

    # make the mock jomnilinkII.Connection disconnect
    omni1.connected.return_value = False
    omni1._disconnect("notConnectedEvent", Mock())

    # and let the disconnect message get processed
    helpers.run_concurrent_thread(plugin, 1)

    # now the device should be in the error state
    for dev in area_devices:
        assert dev.errorState is not None
    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()

    # let the disconnect message get processed
    patched_datetime.fast_forward(minutes=2)

    # allow time for the thread to run by using the real sleep,
    # not the patched one in the plugin
    sleep(0.1)

    # let the reconnect message get processed
    helpers.run_concurrent_thread(plugin, 1)

    for dev in area_devices:
        assert dev.errorState is None


def test_device_stop_comm_succeeds(indigo, plugin, area_devices):
    dev = indigo.devices["Area 2"]
    plugin.deviceStartComm(dev)
    plugin.deviceStopComm(dev)


def test_generate_mode_list_succeeds(indigo, plugin, area_devices):
    dev = indigo.devices["First Area"]
    plugin.deviceStartComm(dev)

    values = {}
    plugin.getActionConfigUiValues(values, "armSecuritySystem", dev.id)
    tups = plugin.generateModeList(None, values, "armSecuritySystem", dev.id)
    assert len(tups) == 7
    assert ("0", "Disarm") in tups
    assert ("3", "Away Mode") in tups


def test_validate_action_config_ui_uses_substitute_check(
        plugin, area_devices, monkeypatch, indigo):
    dev = indigo.devices["First Area"]
    plugin.deviceStartComm(dev)
    values = {}

    plugin.getActionConfigUiValues(values, "armSecuritySystem", dev.id)

    sub = Mock(return_value=(True, ""))
    monkeypatch.setattr(indigo.PluginBase, "substitute", sub)
    values["user"] = "%%blahblah"
    tup = plugin.validateActionConfigUi(values, "armSecuritySystem", 1)

    assert tup[0]
    assert not tup[2]
    assert sub.call_count == 1


def test_validate_action_config_ui_catches_obvious_errors(
        plugin, indigo, omni1, area_devices):

    dev = indigo.devices["First Area"]
    plugin.deviceStartComm(dev)
    values = {}

    plugin.getActionConfigUiValues(values, "armSecuritySystem", dev.id)
    test_values = ["0000", "0", "abc", "999"]
    for value in test_values:
        values["user"] = value
        tup = plugin.validateActionConfigUi(values, "armSecuritySystem", 1)
        assert not tup[0]
        assert "user" in tup[2]


def test_arm_security_system_sends_command(
        plugin, indigo, omni1, area_devices, jomnilinkII):
    dev = indigo.devices["Area 2"]

    omni1.controllerCommand = Mock()
    jomnilinkII.MessageTypes.CommandMessage.CMD_SECURITY_OMNI_DISARM = 48

    action = Mock()
    action.deviceId = dev.id
    action.props = {"user": "1", "mode": 3}

    plugin.armSecuritySystem(action)

    omni1.controllerCommand.assert_called_with(48 + 3, 1, 2)


def test_arm_security_system_catches_scripting_errors(
        plugin, indigo, area_devices):
    dev = indigo.devices["Area 2"]

    action = Mock()
    action.deviceId = dev.id
    action.props = {"user": "99", "mode": 3}

    plugin.armSecuritySystem(action)

    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()

    action.props = {"user": "1", "mode": "abracadabra"}

    plugin.armSecuritySystem(action)

    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_bypass_restore_sends_command(
        plugin, indigo, omni1, area_devices, jomnilinkII):
    dev = indigo.devices["Area 2"]

    omni1.controllerCommand = Mock()
    jomnilinkII.MessageTypes.CommandMessage.CMD_SECURITY_RESTORE_ALL_ZONES = 4

    action = Mock()
    action.pluginTypeId = "restoreAllZones"
    action.deviceId = dev.id
    action.props = {"user": "1"}

    plugin.bypassRestoreZone(action)

    omni1.controllerCommand.assert_called_with(4, 1, 2)


def test_bypass_restore_catches_scripting_errors(
        plugin, indigo, area_devices):
    dev = indigo.devices["Area 2"]

    action = Mock()
    action.pluginTypeId = "restoreAllZones"
    action.deviceId = dev.id
    action.props = {"user": "99"}

    plugin.bypassRestoreZone(action)

    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_validate_code_action_config_ui_uses_substitute_check(
        plugin, area_devices, monkeypatch, indigo):
    values = {}
    dev = indigo.devices["Area 2"]
    plugin.getActionConfigUiValues(values, "checkSecurityCode", dev.id)

    sub = Mock(return_value=(True, ""))
    monkeypatch.setattr(indigo.PluginBase, "substitute", sub)
    values["code"] = "%%blahblah"
    tup = plugin.validateActionConfigUi(values, "checkSecurityCode", 1)

    assert tup[0]
    assert not tup[2]
    assert sub.call_count == 1


def test_validate_code_action_config_ui_catches_obvious_errors(
        plugin, indigo, area_devices):
    dev = indigo.devices["Area 2"]
    values = {}
    plugin.getActionConfigUiValues(values, "checkSecurityCode", dev.id)
    test_values = ["123A", "", "0"]
    for code in test_values:
        values["code"] = code
        tup = plugin.validateActionConfigUi(values, "checkSecurityCode", 1)
        assert not tup[0]
        assert "code" in tup[2]


def test_validate_code_catches_scripting_errors(
        plugin, indigo, area_devices, version):
    dev = indigo.devices["Area 2"]

    action = Mock()
    action.deviceId = dev.id
    action.props = {"actionVersion": version}

    test_values = ["123A", "", "0"]
    for code in test_values:
        action.props["code"] = code
        plugin.checkSecurityCode(action)
        assert plugin.errorLog.called
        plugin.errorLog.reset_mock()


def test_check_security_code_updates_device_states_on_valid_code(
        plugin, indigo, area_devices, omni1, version):
    dev = indigo.devices["First Area"]
    plugin.deviceStartComm(dev)

    mock_scv = jomni_mimic.SecurityCodeValidation(16, 2)
    omni1.reqSecurityCodeValidation = Mock(return_value=mock_scv)

    action = Mock()
    action.deviceId = dev.id
    action.props = {"code": "9876", "actionVersion": version}

    plugin.checkSecurityCode(action)

    omni1.reqSecurityCodeValidation.assert_called_with(1, 9, 8, 7, 6)
    assert dev.states["lastCheckedCode"] == action.props["code"]
    assert dev.states["lastCheckedCodeAuthority"] == "Manager"
    assert dev.states["lastCheckedCodeUser"] == 16
    assert not dev.states["lastCheckedCodeDuress"]


def test_check_security_code_handles_network_error(
        plugin, indigo, area_devices, omni1, py4j, version):
    dev = indigo.devices["First Area"]
    plugin.deviceStartComm(dev)
    omni1.reqSecurityCodeValidation = Mock(
        side_effect=py4j.protocol.Py4JError)

    action = Mock()
    action.deviceId = dev.id
    action.props = {"code": "9876", "actionVersion": version}
    assert not plugin.errorLog.called

    plugin.checkSecurityCode(action)

    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()

    assert dev.states["lastCheckedCode"] == action.props["code"]
    assert dev.states["lastCheckedCodeAuthority"] == "Error"
    assert dev.states["lastCheckedCodeUser"] == "N/A"
    assert not dev.states["lastCheckedCodeDuress"]



def test_concurrent_thread_counts_down_timers(
        plugin, indigo, jomnilinkII, omni1, area_devices, patched_datetime):
    dev = indigo.devices["Area 2"]
    plugin.deviceStartComm(dev)

    status_msg = jomni_mimic.ObjectStatus(
        jomnilinkII.Message.OBJ_TYPE_AREA,
        [jomni_mimic.AreaStatus(2, 2, 0, 30, 10)])

    # send notification with nonzero timers
    omni1._notify("objectStausNotification", status_msg)

    # allow run_concurrent_thread to update them
    helpers.run_concurrent_thread(plugin, 1)

    assert dev.states["entryTimer"] == 30
    assert dev.states["exitTimer"] == 10

    patched_datetime.fast_forward(seconds=20)
    helpers.run_concurrent_thread(plugin, 1)

    assert dev.states["entryTimer"] == 10
    assert dev.states["exitTimer"] == 0

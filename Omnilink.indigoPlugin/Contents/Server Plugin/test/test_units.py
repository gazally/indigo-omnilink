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

from mock import Mock
import pytest

import fixtures.jomnilinkII as jomni_mimic


def create_unit_devices(plugin, indigo, values, unit_types,
                        device_connection_props):
    values = plugin.makeConnection(values, [])
    values["deviceGroupList"] = ["omniStandardUnit", "omniRadioRAUnit",
                                 "omniFlagUnit", "omniVoltageUnit"]
    values["prefix"] = "test"
    plugin.createDevices(
        values, [dev.id for dev in indigo.devices.iter()
                 if dev.pluginProps["url"] == device_connection_props["url"]])
    return values


def get_unit_devices(indigo, values, unit_types, device_connection_props):
    return [dev for dev in indigo.devices.iter()
            if (dev.deviceTypeId in unit_types and
                dev.pluginProps["url"] == device_connection_props["url"])]


@pytest.fixture
def unit_devices(plugin, indigo, device_factory_fields, omni_unit_types,
                 device_connection_props):
    create_unit_devices(plugin, indigo, device_factory_fields, omni_unit_types,
                        device_connection_props)
    return get_unit_devices(indigo, device_factory_fields, omni_unit_types,
                            device_connection_props)


def test_get_device_list_returns_unit(plugin, omni1, omni_unit_types,
                                      device_factory_fields):
    plugin.makeConnection(device_factory_fields, [])
    result = plugin.getDeviceGroupList(None, device_factory_fields, [])
    assert omni1.reqObjectProperties.called
    for t in omni_unit_types:
        assert t in [k for k, v in result]


def test_get_device_list_returns_empty_list_on_connection_error(
        plugin, py4j, device_factory_fields, omni1, omni_unit_types):
    values = plugin.makeConnection(device_factory_fields, [])

    omni1.reqObjectProperties.side_effect = py4j.protocol.Py4JError

    result = plugin.getDeviceGroupList(None, values, [])

    for t in omni_unit_types:
        assert t not in [k for k, v in result]
    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_notification_ignores_non_unit_notifications(
        plugin, indigo, device_factory_fields, omni1, omni_unit_types,
        device_connection_props):
    status_msg = jomni_mimic.ObjectStatus(Mock(),
                                          [Mock(side_effect=AssertionError)])
    create_unit_devices(plugin, indigo, device_factory_fields,
                        omni_unit_types, device_connection_props)
    omni1._notify("objectStausNotification", status_msg)


def test_create_devices_creates_device_for_each_unit(
        plugin, unit_devices, device_factory_fields, indigo,
        omni_unit_types, device_connection_props):
    assert len(unit_devices) == 3

    plugin.createDevices(device_factory_fields,
                         [dev.id for dev in unit_devices])

    assert len(get_unit_devices(indigo, device_factory_fields,
                                omni_unit_types, device_connection_props)) == 3


def test_device_start_comm_succeeds_on_valid_input(
        plugin, indigo, unit_devices, req_object_status_unit_states):
    dev = indigo.devices["test X10 Unit"]

    plugin.deviceStartComm(dev)

    assert dev.error_state is None
    for k, v in req_object_status_unit_states.items():
        assert dev.states[k] == v

    assert dev.states["name"] == "X10 Unit"


def test_device_start_comm_sets_error_state_on_connection_error(
        plugin, indigo, py4j, omni1, unit_devices):
    dev = indigo.devices["test X10 Unit"]
    omni1.reqObjectStatus.side_effect = py4j.protocol.Py4JError

    plugin.deviceStartComm(dev)
    assert dev.error_state is not None


def test_remove_devices_removes_unit_devices(
        plugin, indigo, unit_devices, device_factory_fields, omni_unit_types,
        device_connection_props):
    dev_ids = [dev.id for dev in unit_devices]
    assert len(dev_ids) > 0
    plugin.removeDevices(device_factory_fields, dev_ids)
    devices = get_unit_devices(indigo, device_factory_fields, omni_unit_types,
                               device_connection_props)
    assert not devices


def test_notification_changes_device_state(
        plugin, indigo, omni1, unit_devices, jomnilinkII_message):

    dev = indigo.devices["test Radio RA"]
    plugin.deviceStartComm(dev)
    assert not dev.states["onOffState"]
    assert dev.states["brightnessLevel"] == 0
    assert not plugin.errorLog.called

    status_msg = jomni_mimic.ObjectStatus(jomnilinkII_message.OBJ_TYPE_UNIT,
                                          [jomni_mimic.UnitStatus(2, 1, 100)])

    omni1._notify("objectStausNotification", status_msg)

    assert dev.states["onOffState"]
    assert dev.states["brightnessLevel"] == 1
    assert dev.states["timeLeftSeconds"] == 100
    assert dev.error_state is None


def test_disconnect_sets_error_state_of_correct_unit_device(
        plugin, indigo, unit_devices, device_factory_fields,
        device_connection_props_2,
        device_factory_fields_2, omni2, omni_unit_types):

    create_unit_devices(plugin, indigo, device_factory_fields_2,
                        omni_unit_types, device_connection_props_2)
    unit_devices_2 = get_unit_devices(indigo, device_factory_fields_2,
                                      omni_unit_types,
                                      device_connection_props_2)
    assert len(unit_devices_2) == 3

    for dev in unit_devices + unit_devices_2:
        plugin.deviceStartComm(dev)

    omni2._disconnect("notConnectedEvent", Mock())

    for dev in unit_devices:
        assert dev.error_state is None
    for dev in unit_devices_2:
        assert dev.error_state is not None


def test_reconnect_notification_clears_device_error_state(
        plugin, indigo, unit_devices, omni1):

    for dev in unit_devices:
        plugin.deviceStartComm(dev)

    omni1.connected.return_value = False
    omni1._disconnect("notConnectedEvent", Mock())

    assert dev.error_state is not None
    plugin.update()  # this should get the second connection object
    assert dev.error_state is None


def test_device_stop_comm_succeeds(plugin, indigo, unit_devices):
    dev = indigo.devices["test Voltage"]
    plugin.deviceStartComm(dev)
    plugin.deviceStopComm(dev)


def test_action_command_dimmer_relay_sends_commands(
        plugin, indigo, omni1, unit_devices):
    dev = indigo.devices["test Radio RA"]
    plugin.deviceStartComm(dev)

    action = Mock()
    k = indigo.kDimmerRelayAction
    actions = ["TurnOn", "TurnOff", "Toggle", "SetBrightness",
               "BrightenBy", "DimBy"]
    params = [0, 0, 0, 40, 20, 30]
    for i, a, p in zip(range(len(actions)), actions, params):
        setattr(k, a, i)
        action.deviceAction = i
        action.actionValue = params[i]
        plugin.actionControlDimmerRelay(action, dev)

    assert omni1.controllerCommand.call_count == len(actions)


def test_action_request_status_succeeds(
        plugin, indigo, omni1, unit_devices):
    dev = indigo.devices["test Radio RA"]
    plugin.deviceStartComm(dev)

    action = Mock()
    action.deviceAction = indigo.kDeviceGeneralAction.RequestStatus
    plugin.actionControlGeneral(action, dev)


def test_action_request_logs_network_error(
        plugin, indigo, py4j, omni1, unit_devices):
    dev = indigo.devices["test X10 Unit"]
    plugin.deviceStartComm(dev)

    action = Mock()
    action.deviceAction = indigo.kDimmerRelayAction.Toggle
    omni1.controllerCommand.side_effect = py4j.protocol.Py4JError

    plugin.actionControlDimmerRelay(action, dev)
    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()

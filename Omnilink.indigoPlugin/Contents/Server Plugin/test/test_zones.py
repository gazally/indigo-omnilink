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

import pytest

from mock import Mock, MagicMock

import fixtures.jomnilinkII as jomni_mimic


def create_zone_devices(plugin, indigo, values):
    values = plugin.makeConnection(values, [])
    values["deviceGroupList"] = ["omniZoneDevice"]
    plugin.createDevices(
        values,
        [dev.id for dev in indigo.devices.iter()
         if dev.pluginProps["ipAddress"] == values["ipAddress"]])
    return [dev for dev in indigo.devices.iter()
            if (dev.deviceTypeId == "omniZoneDevice" and
                dev.pluginProps["ipAddress"] == values["ipAddress"])]


@pytest.fixture
def zone_devices(plugin, indigo, device_factory_fields):
    """ Ask the plugin to create one batch of zone devices, return a list
    of them. """
    return create_zone_devices(plugin, indigo, device_factory_fields)


@pytest.fixture
def zone_devices_2(plugin, indigo, device_factory_fields_2, zone_devices):
    """ Ask the plugin to create zone devices on omni2 """
    return create_zone_devices(plugin, indigo, device_factory_fields_2)


def test_get_device_list_returns_zone(plugin, device_factory_fields, omni1):
    plugin.makeConnection(device_factory_fields, [])
    result = plugin.getDeviceGroupList(None, device_factory_fields, [])
    assert omni1.reqObjectProperties.called
    assert ("omniZoneDevice", "Zone") in result


def test_get_device_list_returns_empty_list_on_connection_error(
        plugin, plugin_module, device_factory_fields, omni1):
    plugin.makeConnection(device_factory_fields, [])

    ConnectionError = plugin_module.ConnectionError
    omni1.reqObjectProperties.side_effect = ConnectionError

    result = plugin.getDeviceGroupList(None, device_factory_fields, [])

    assert ("omniZoneDevice", "Zone") not in result
    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_create_devices_creates_device_for_each_zone(
        indigo, plugin, device_factory_fields, zone_devices):
    assert (len([dev for dev in indigo.devices.iter()
                 if dev.deviceTypeId == "omniZoneDevice"]) == 3)

    plugin.createDevices(device_factory_fields,
                         [dev.id for dev in indigo.devices.iter()])

    assert (len([dev for dev in indigo.devices.iter()
                 if dev.deviceTypeId == "omniZoneDevice"]) == 3)


def test_device_start_comm_succeeds_on_valid_input(
        indigo, plugin, zone_devices,
        req_object_props_zone_states,
        req_object_status_zone_states):

    for dev in zone_devices:
        plugin.deviceStartComm(dev)

    for dev in zone_devices:
        assert dev.error_state is None
        right_answers = req_object_props_zone_states[dev.name]
        for k, v in right_answers.items():
            assert dev.states[k] == v
        for k, v in req_object_status_zone_states.items():
            assert dev.states[k] == v


def test_device_start_comm_wont_start_old_device(indigo, plugin, zone_devices):
    dev = indigo.devices["Front Door"]
    dev.pluginProps["deviceVersion"] = "0.0"
    plugin.deviceStartComm(dev)
    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_device_start_comm_sets_error_state_on_connection_error(
        indigo, py4j, plugin, omni1, zone_devices):
    dev = indigo.devices["Smoke Det"]
    omni1.reqObjectStatus.side_effect = py4j.protocol.Py4JError

    plugin.deviceStartComm(dev)
    assert dev.error_state is not None
    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_remove_devices_removes_zone_devices(plugin, indigo, zone_devices,
                                             device_factory_fields):
    dev_ids = [dev.id for dev in zone_devices]
    plugin.removeDevices(device_factory_fields, dev_ids)
    for dev in indigo.devices.iter():
        assert dev.deviceTypeId != "omniZoneDevice"


def test_notification_changes_device_state(plugin, indigo, zone_devices,
                                           jomnilinkII, omni1):
    dev = indigo.devices["Front Door"]
    plugin.deviceStartComm(dev)
    assert dev.states["condition"] == "Secure"
    assert not plugin.errorLog.called

    status_msg = jomni_mimic.ObjectStatus(jomnilinkII.Message.OBJ_TYPE_ZONE,
                                          [jomni_mimic.ZoneStatus(1, 1, 100)])

    omni1._notify("objectStausNotification", status_msg)

    assert dev.states["condition"] == "Not Ready"
    assert not dev.states["onOffState"]
    assert dev.error_state is None


def test_notification_ignores_non_zone_notifications(plugin, indigo, omni1,
                                                     zone_devices):
    status_msg = jomni_mimic.ObjectStatus(Mock(),
                                          [jomni_mimic.ZoneStatus(1, 1, 100)])
    dev = indigo.devices["Front Door"]
    plugin.deviceStartComm(dev)
    omni1._notify("objectStausNotification", status_msg)
    assert dev.states["condition"] == "Secure"


def test_disconnect_notification_sets_error_state_of_correct_zone_device(
        plugin, indigo, zone_devices, device_factory_fields,
        omni2, zone_devices_2, device_factory_fields_2):

    assert len(zone_devices_2) == 3

    for dev in zone_devices + zone_devices_2:
        plugin.deviceStartComm(dev)

    omni2._disconnect("notConnectedEvent", Mock())

    for dev in zone_devices:
        assert dev.error_state is None
    for dev in zone_devices_2:
        assert dev.error_state is not None


def test_reconnect_notification_clears_device_error_state(plugin, indigo,
                                                          zone_devices, omni1):
    for dev in zone_devices:
        plugin.deviceStartComm(dev)

    omni1.connected.return_value = False
    omni1._disconnect("notConnectedEvent", Mock())

    for dev in zone_devices:
        assert dev.error_state is not None
    plugin.update()  # this should get the second connection object
    for dev in zone_devices:
        assert dev.error_state is None


def test_zone_extension_logs_error_on_unimplemented_sensor_change(
        plugin, indigo, zone_devices):
    dev = indigo.devices["Smoke Det"]
    plugin.deviceStartComm(dev)
    action = Mock()
    action.sensorAction = indigo.kSensorAction.TurnOn

    plugin.actionControlSensor(action, dev)
    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_zone_extension_logs_error_on_unimplemented_sensor_beep(
        plugin, indigo, zone_devices):
    dev = indigo.devices["Front Door"]
    plugin.deviceStartComm(dev)
    action = Mock()
    action.deviceAction = indigo.kDeviceGeneralAction.Beep

    plugin.actionControlGeneral(action, dev)
    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_zones_update_sensor_on_request_status_action(
        plugin, indigo, zone_devices, jomnilinkII, omni1):
    dev = indigo.devices["Front Door"]
    plugin.deviceStartComm(dev)

    action = Mock()
    action.deviceAction = indigo.kDeviceGeneralAction.RequestStatus
    status_msg = jomni_mimic.ObjectStatus(jomnilinkII.Message.OBJ_TYPE_ZONE,
                                          [jomni_mimic.ZoneStatus(1, 1, 100)])
    omni1.reqObjectStatus = Mock(return_value=status_msg)

    plugin.actionControlGeneral(action, dev)

    assert dev.states["condition"] == "Not Ready"
    assert not dev.states["onOffState"]


def test_request_status_action_logs_error_on_connection_error(
        plugin, indigo, py4j, zone_devices, omni1):
    dev = indigo.devices["Front Door"]
    plugin.deviceStartComm(dev)

    action = Mock()
    action.deviceAction = indigo.kDeviceGeneralAction.RequestStatus
    omni1.reqObjectStatus.side_effect = py4j.protocol.Py4JError

    plugin.actionControlGeneral(action, dev)

    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_device_stop_comm_succeeds(indigo, plugin, zone_devices):
    dev = indigo.devices["Motion"]
    plugin.deviceStartComm(dev)
    plugin.deviceStopComm(dev)

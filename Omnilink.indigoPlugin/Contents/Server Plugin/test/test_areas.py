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
         if dev.pluginProps["url"] == device_connection_props["url"]])
    return [dev for dev in indigo.devices.iter()
            if (dev.deviceTypeId == "omniAreaDevice" and
                dev.pluginProps["url"] == device_connection_props["url"])]


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
        assert dev.error_state is None
        right_answers = req_object_props_area_states[dev.name]
        for k, v in right_answers.items():
            assert dev.states[k] == v

def test_device_start_comm_sets_error_state_on_connection_error(
        indigo, py4j, plugin, omni1, area_devices):
    dev = indigo.devices["First Area"]
    omni1.reqObjectStatus.side_effect = py4j.protocol.Py4JError

    plugin.deviceStartComm(dev)
    assert dev.error_state is not None


def test_remove_devices_removes_area_devices(plugin, indigo, area_devices,
                                             device_factory_fields):
    dev_ids = [dev.id for dev in area_devices]
    plugin.removeDevices(device_factory_fields, dev_ids)
    for dev in indigo.devices.iter():
        assert dev.deviceTypeId != "omniAreaDevice"


def test_notification_changes_device_state(plugin, indigo, area_devices,
                                           jomnilinkII, omni1):
    dev = indigo.devices["Area 2"]
    plugin.deviceStartComm(dev)
    assert dev.states["mode"] == "Off"
    assert not plugin.errorLog.called

    status_msg = jomni_mimic.ObjectStatus(jomnilinkII.Message.OBJ_TYPE_AREA,
                                          [jomni_mimic.AreaStatus(2, 2, 0, 0, 0)])

    omni1._notify("objectStausNotification", status_msg)
    helpers.run_concurrent_thread(plugin, 1)

    assert dev.states["mode"] == "Night"
    assert dev.error_state is None


def test_notification_ignores_non_area_notifications(plugin, indigo, omni1,
                                                     area_devices):
    status_msg = jomni_mimic.ObjectStatus(Mock(),
                                          [jomni_mimic.UnitStatus(1, 1, 100)])
    dev = indigo.devices["First Area"]
    plugin.deviceStartComm(dev)

    omni1._notify("objectStausNotification", status_msg)
    helpers.run_concurrent_thread(plugin, 1)

    assert dev.states["mode"] == "Off"


def test_disconnect_notification_sets_error_state_of_correct_area_device(
        plugin, indigo, area_devices, device_factory_fields,
        omni2, area_devices_2, device_factory_fields_2):

    assert len(area_devices_2) == 2

    for dev in area_devices + area_devices_2:
        plugin.deviceStartComm(dev)

    omni2._disconnect("notConnectedEvent", Mock())

    helpers.run_concurrent_thread(plugin, 1)

    for dev in area_devices:
        assert dev.error_state is None
    for dev in area_devices_2:
        assert dev.error_state is not None

    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_reconnect_notification_clears_device_error_state(
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
        assert dev.error_state is not None
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
        assert dev.error_state is None


def test_device_stop_comm_succeeds(indigo, plugin, area_devices):
    dev = indigo.devices["Area 2"]
    plugin.deviceStartComm(dev)
    plugin.deviceStopComm(dev)

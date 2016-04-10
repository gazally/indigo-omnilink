#! /usr/bin/env python
# Unit Tests for Omnilink Plugin for Indigo Server
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

import fixtures.jomnilinkII as jomni_mimic
import fixtures.helpers as helpers


def test_error_reported_on_failure_to_start_java(plugin_module, version, popen,
                                                 jomnilinkII):
    popen.side_effect = OSError

    props = {"showDebugInfo": False,
             "showJomnilinkIIDebugInfo": False}
    plugin = plugin_module.Plugin("", "", version, props)
    plugin.startup()

    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_shutdown_handles_exceptions(plugin, gateway, py4j):
    gateway.shutdown.side_effect = py4j.protocol.Py4JError

    plugin.shutdown()

    assert gateway.shutdown.called
    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_plugin_dispatches_to_pluginbase(plugin, indigo, monkeypatch):
    indigo.PluginBase.actionControlSprinkler = Mock()
    plugin.actionControlSprinkler(Mock(), Mock())
    assert indigo.PluginBase.actionControlSprinkler.called


def test_debug_menu_item_toggles(plugin):
    assert not plugin.debug
    plugin.debugLog.reset_mock()

    plugin.toggleDebugging()

    assert plugin.debugLog.call_count == 1
    assert plugin.debug

    plugin.toggleDebugging()

    assert plugin.debugLog.call_count == 3
    assert not plugin.debug
    assert not plugin.errorLog.called


def test_jomnilinkii_debug_menu_item_toggles(plugin):
    assert not plugin.debug_omni
    plugin.debugLog.reset_mock()

    plugin.toggleJomnilinkIIDebugging()

    assert plugin.debugLog.call_count == 1
    assert plugin.debug_omni

    plugin.toggleJomnilinkIIDebugging()

    assert plugin.debugLog.call_count == 2
    assert not plugin.debug_omni
    assert not plugin.errorLog.called


def test_run_concurrent_thread(plugin):
    helpers.run_concurrent_thread(plugin, 5)


def test_interactive_interpreter_menu_item_succeeds(plugin, monkeypatch):
    p = Mock()
    monkeypatch.setattr("plugin.start_shell_thread", p)
    plugin.startInteractiveInterpreter()
    assert p.called


def test_prefs_ui_validation_succeeds_on_valid_input(plugin):
    values = {"showDebugInfo": True,
              "showJomnilinkIIDebugInfo": True}

    ok, d, e = plugin.validatePrefsConfigUi(values)
    assert ok

    values["showDebugInfo"] = False
    ok, d, e = plugin.validatePrefsConfigUi(values)
    assert ok


def test_device_factory_uivalidation_succeeds_on_valid_input(
        plugin, device_factory_fields):
    ok, d, e = plugin.validateDeviceFactoryUi(device_factory_fields, [])
    assert ok
    assert not plugin.errorLog.called


def test_device_factory_uivalidation_fails_invalid_input(
        plugin, invalid_device_factory_fields):
    values, errorkeys = invalid_device_factory_fields

    ok, d, e = plugin.validateDeviceFactoryUi(values, [])

    assert not ok
    for k in errorkeys:
        assert k in e


def test_make_connection_clears_error_state_on_valid_input(
        plugin, device_factory_fields):
    values = dict(device_factory_fields)
    errors = {"portNumberError": True,
              "encryptionKey1Error": True,
              "encryptionKey2Error": True,
              "error": True}

    values.update(errors)

    values = plugin.makeConnection(values, [])

    for k in errors.keys():
        assert not values[k]
    assert not values["connectionError"]
    assert values["isConnected"]


def test_make_connection_sets_error_state_on_invalid_input(
        plugin, invalid_device_factory_fields):
    values, errorkeys = invalid_device_factory_fields

    values = plugin.makeConnection(values, [])

    assert values["error"]
    for k in errorkeys:
        assert values[k + "Error"]
    assert not values["isConnected"]


def test_make_connection_sets_error_state_on_failure_to_connect(
        plugin, py4j, jomnilinkII, device_factory_fields):
    jomnilinkII.Connection.side_effect = py4j.protocol.Py4JJavaError("test")

    values = plugin.makeConnection(device_factory_fields, [])

    assert values["error"]
    keys = ["portNumber", "encryptionKey1", "encryptionKey2"]
    for k in keys:
        assert not values[k + "Error"]
    assert values["connectionError"]
    assert not values["isConnected"]
    assert plugin.errorLog.called
    plugin.errorLog.reset_mock()


def test_get_device_factory_uivalues_handles_empty_device_list(plugin):
    values, errors = plugin.getDeviceFactoryUiValues([])
    assert len(errors) == 0
    assert "isConnected" not in values or not values["isConnected"]


def test_get_device_factory_uivalues_makes_connection_given_device(
        indigo, plugin, device_factory_fields):
    dev = indigo.device.create(Mock(), "omniControllerDevice",
                               device_factory_fields)

    values, errors = plugin.getDeviceFactoryUiValues([dev.id])
    assert len(errors) == 0
    assert values["isConnected"]


def recurse_elem(root):
    """ recursively iterate the elements of an XML tree """
    for elem in root:
        yield elem
        for subelem in recurse_elem(elem):
            yield subelem


def iterate_callbacks(root):
    """ traverse an xml tree and yield all the callback methods found """
    for e in recurse_elem(root):
        if e.tag == "CallbackMethod":
            yield e.text
        elif "method" in e.attrib:
            yield e.attrib["method"]


def test_callbacks_exist(plugin, xmls):
    missing = set()
    for method in list(iterate_callbacks(xmls.values())):
        if (not hasattr(plugin, method) or
                not callable(getattr(plugin, method))):
            missing.add(method)
    assert not missing


def test_plugin_extensions_match_xml_ids(plugin, xmls):
    action_ids = [a.attrib["id"] for a in xmls["Actions"]
                  if a and a.tag == "Action"]
    for a in action_ids:
        assert a in plugin.type_ids_map["action"].keys()

    device_ids = [d.attrib["id"] for d in xmls["Devices"]
                  if d and d.tag == "Device"]
    for d in device_ids:
        assert d in plugin.type_ids_map["device"].keys()

    event_ids = [e.attrib["id"] for e in xmls["Events"]
                 if e and e.tag == "Event"]
    for e in event_ids:
        assert e in plugin.type_ids_map["event"].keys()


def test_write_controller_info_to_log_succeeds(plugin, omnis, jomnilinkII,
                                               device_factory_fields,
                                               device_factory_fields_2):
    mock_capacities = Mock()
    mock_capacities.getCapacity.return_value = 2
    mock_features = Mock()
    mock_features.getFeatures.return_value = ["features"]
    mock_statuses = Mock()
    mock_statuses.getStatuses.return_value = [Mock()]
    mock_log = create_uploadEventLogData(jomnilinkII)

    for omni in omnis:
        omni.reqObjectTypeCapacities.return_value = mock_capacities
        omni.reqSystemFeatures.return_value = mock_features
        omni.uploadEventLogData = mock_log

    plugin.makeConnection(device_factory_fields, [])
    plugin.makeConnection(device_factory_fields_2, [])
    plugin.writeControllerInfoToLog()


def test_write_controller_info_to_log_handles_failed_startup(
        indigo, plugin, omni1, omni2, jomnilinkII, monkeypatch,
        device_factory_fields):
    plugin.makeConnection(device_factory_fields, [])
    omni1.connected.return_value = False
    omni2.connected.return_value = False
    indigo.server.log.reset_mock()

    plugin.writeControllerInfoToLog()

    indigo.server.log.call_count == 1
    args, kwargs = indigo.server.log.call_args
    assert "is not connected" in args[0]


def create_uploadEventLogData(jomnilinkII):
    mtype = jomnilinkII.Message.MESG_TYPE_EVENT_LOG_DATA = 99

    class locals:
        objs = [
            jomni_mimic.EventLogData(
                mtype, 0, 3, 28, 10, 30, 135, 8, 0, True),
            jomni_mimic.EventLogData(
                mtype, 0, 3, 28, 10, 30, 4, 254, 4, True),
            jomni_mimic.EventLogData(
                mtype, 0, 3, 28, 10, 30, 138, 0, 1, False),
            jomni_mimic.EventLogData(
                0, 0, 3, 28, 10, 30, 0, 0, 0, False)]
        index = 0

    def looper(a, b):
        retval = locals.objs[locals.index % len(locals.objs)]
        locals.index += 1
        return retval

    return looper

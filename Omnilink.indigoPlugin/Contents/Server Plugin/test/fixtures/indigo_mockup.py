#! /usr/bin/env python
# Fixtures for testing Indigo plugins
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
from __future__ import unicode_literals
from __future__ import print_function
import os
import sys
import xml.etree.ElementTree as ET

from mock import Mock, MagicMock
import pytest


@pytest.fixture(scope="session")
def plugin_path():
    """ Return the path where the plugin xmls can be found """
    return os.getcwd()


@pytest.fixture(scope="session")
def xmls(plugin_path):
    """ Session-scoped fixture that imports the xml files """
    contents = {}
    for name in ["Actions", "Devices", "Events", "MenuItems", "PluginConfig"]:
        fullname = os.path.join(plugin_path, name + ".xml")
        if os.path.exists(fullname):
            contents[name] = ET.parse(fullname).getroot()
        else:
            contents[name] = []
    return contents


@pytest.fixture(autouse=True)
def indigo(plugin_module):
    """ Reset the indigo mockup and return it """
    plugin_module.indigo._reset()
    return plugin_module.indigo


@pytest.fixture(scope="session")
def mock_indigo(xmls):
    """ Return a MagicMock with enough functionality attached to impersonate
    the indigo module. """
    class PluginBaseForTest(object):
        """ Mockup of indigo.PluginBase, for testing """
        def __init__(self, pid, name, version, prefs):
            self.pluginPrefs = prefs

        def substitute(self, string, validateOnly=False):
            if validateOnly:
                return (True, string)
            else:
                return string

        def deviceStartComm(self, dev):
            pass

        def deviceStopComm(self, dev):
            pass

        debugLog = Mock(side_effect=print)
        errorLog = Mock(side_effect=print)
        sleep = Mock()

        @classmethod
        def _reset(cls):
            cls.debugLog.reset_mock()
            cls.errorLog.reset_mock()
            cls.sleep.reset_mock()

    class IndigoDictForTest(dict):
        """ Mockup of indigo.Dict, for testing """
        def iter(self, whatever=None):
            return list(set(self.values()))

    class DeviceForTest(object):
        """ Mockup of indigo.device, for testing """

        _dev_id = 1000
        devices = IndigoDictForTest()
        _device_defns = [child for child in xmls["Devices"]
                         if child.tag == "Device"]
        _device_type_ids = [defn.attrib["id"] for defn in _device_defns]
        for defn in _device_defns:
            assert defn.attrib["type"] in ["custom", "relay", "dimmer",
                                           "sensor"], defn.attrib["id"]

        @classmethod
        def _reset(cls):
            _dev_id = 1000
            devices = IndigoDictForTest()

        @classmethod
        def _get_device_defn(cls, device_type):
            defns = [defn for defn in cls._device_defns
                     if defn.attrib['id'] == device_type]
            assert len(defns) == 1, device_type
            return defns[0]

        @classmethod
        def _get_device_state_list(cls, device_type):
            defn = cls._get_device_defn(device_type)
            states = [child for child in defn if child.tag == "States"][0]
            state_ids = [st.attrib["id"] for st in states if st.tag == "State"]
            defn_type = defn.attrib["type"]

            if defn_type in ["relay", "dimmer", "sensor"]:
                state_ids.append("onOffState")
            if defn_type == "sensor":
                state_ids.append("sensorValue")
            if defn_type == "dimmer":
                state_ids.append("brightnessLevel")
            return state_ids

        @classmethod
        def create_device(cls, protocol, deviceTypeId, props=None, name=None):
            assert deviceTypeId in cls._device_type_ids, deviceTypeId
            if props is None:
                props = {}
            cls._dev_id += 1
            if name is None:
                name = "new device " + str(cls._dev_id)
            dev = DeviceForTest(cls._dev_id, deviceTypeId, name, props)
            cls.devices[cls._dev_id] = dev
            cls.devices[name] = dev
            return dev

        @classmethod
        def delete_device(cls, device):
            keys = [k for k, v in cls.devices.items() if v is device]
            for k in keys:
                del cls.devices[k]

        def __init__(self, dev_id, deviceTypeId, name, props):
            self.id = dev_id
            self.deviceTypeId = deviceTypeId
            self.name = name
            self.pluginProps = dict(props)
            self.states = {}
            self.configured = True
            self.enabled = True
            self.error_state = None
            self.model = ""
            self.subModel = ""

        def updateStateOnServer(self, key=None, value=None,
                                clearErrorState=True, uiValue=""):
            assert key is not None
            assert value is not None
            assert key in DeviceForTest._get_device_state_list(
                self.deviceTypeId), (
                    self.deviceTypeId + " does not have state " + key)
            self.states[key] = value

        def setErrorStateOnServer(self, msg):
            self.error_state = msg

        def replacePluginPropsOnServer(self, props):
            self.pluginProps = props

        def refreshFromServer(self):
            pass

        def replaceOnServer(self):
            pass

        def stateListOrDisplayStateIdChanged(self):
            pass

        @property
        def onState(self):
            return self.states["onOffState"]

        @property
        def brightness(self):
            return self.states["brightnessLevel"]

    indigo_mock = MagicMock()

    indigo_mock.PluginBase = PluginBaseForTest
    indigo_mock.server.log = Mock(side_effect=print)

    indigo_mock.Dict = dict
    indigo_mock.devices = DeviceForTest.devices
    indigo_mock.device.create = Mock(side_effect=DeviceForTest.create_device)
    indigo_mock.device.delete = Mock(side_effect=DeviceForTest.delete_device)

    def reset():
        indigo_mock.reset_mock()
        PluginBaseForTest._reset()
        DeviceForTest._reset()

    reset()
    indigo_mock._reset.side_effect = reset
    sys.modules["indigo"] = indigo_mock
    return indigo_mock

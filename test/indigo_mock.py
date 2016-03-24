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

from mock import patch, Mock, MagicMock


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

    
class IndigoDictForTest(dict):
    """ Mockup of indigo.Dict, for testing """
    def iter(self, whatever):
        return self.values()

    
class DeviceForTest(object):
    """ Mockup of indigo.device, for testing """
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
    def updateStateOnServer(self, key=None, value=None, clearErrorState=True):
        assert key is not None
        assert value is not None
        self.states[key] = value
    def setErrorStateOnServer(self,msg):
        self.error_state = msg
    def replacePluginPropsOnServer(self, props):
        self.pluginProps = props
    def refreshFromServer(self):
        pass
    def replaceOnServer(self):
        pass
    def stateListOrDisplayStateIdChanged(self):
        pass



mock_indigo = MagicMock()
mock_indigo.Dict = dict
mock_indigo.PluginBase = PluginBaseForTest
PluginBaseForTest.debugLog = Mock(side_effect=print)
PluginBaseForTest.errorLog = Mock(side_effect=print)
mock_indigo.server.log = Mock(side_effect=print)
PluginBaseForTest.sleep = Mock()
mock_indigo.devices = IndigoDictForTest()


dev_id = 1000
def create_device(protocol, deviceTypeId, props=None, name=None):
    global dev_id
    global mock_indigo
    if props is None:
        props = {}
    dev_id += 1
    if name is None:
        name = "new device " + str(dev_id)
    dev = DeviceForTest(dev_id, deviceTypeId, name, props)
    mock_indigo.devices[dev_id] = dev
    mock_indigo.devices[name] = dev
    return dev

def delete_device(device):
    keys = [k for k,v in mock_indigo.devices.items() if v is device]
    for k in keys:
        del mock_indigo.devices[k]

def reset():
    mock_indigo.devices = IndigoDictForTest()
    PluginBaseForTest.debugLog.reset_mock()
    PluginBaseForTest.errorLog.reset_mock()
    
mock_indigo.device.create = Mock(side_effect=create_device)
mock_indigo.device.delete = Mock(side_effect=delete_device)


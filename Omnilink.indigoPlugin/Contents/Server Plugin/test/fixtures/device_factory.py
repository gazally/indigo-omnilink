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

import pytest


@pytest.fixture
def device_factory_defaults(xmls):
    results = {}
    df = [d for d in xmls["Devices"] if d.tag == "DeviceFactory"][0]
    ui = [e for e in df if e.tag == "ConfigUI"][0]
    for field in ui:
        value = ""
        if field.attrib["type"] == "textfield":
            if "defaultValue" in field.attrib:
                value = field.attrib["defaultValue"]
        elif field.attrib["type"] == "checkbox":
            if "defaultValue" in field.attrib:
                value = field.attrib["defaultValue"] == "true"
            else:
                value = False
        results[field.attrib["id"]] = value
    return results


@pytest.fixture
def device_factory_valid_input(enckey1, enckey2):
    """ Return some valid user input for the device factory dialog """
    return {"ipAddress": "192.168.1.42",
            "portNumber": "4444",
            "hiddenencryptionKey1": enckey1,
            "hiddenencryptionKey2": enckey2,
            "prefix": ""}


@pytest.fixture
def device_connection_props():
    """ Return connection parameters corresponding to
    device_factory_valid_input """
    return {"address": "192.168.1.42:4444",
            "prefix": ""}


@pytest.fixture
def enckey1():
    return "01-23-45-67-89-AB-CD-EF"


@pytest.fixture
def enckey2():
    return "01-23-45-67-89-AB-CD-EF"


@pytest.fixture
def device_factory_fields(device_factory_defaults, plugin,
                          device_factory_valid_input):
    """ Return UI values set up with valid user input """
    dialog = dict(device_factory_defaults)
    values, _ = plugin.getDeviceFactoryUiValues([])
    dialog.update(values)
    dialog.update(device_factory_valid_input)
    return dialog


@pytest.fixture
def device_factory_valid_input_2(enckey1, enckey2):
    """ Return some different valid user input for the device factory dialog
    """
    return {"ipAddress": "10.0.0.2",
            "portNumber": "4444",
            "hiddenencryptionKey1": enckey1,
            "hiddenencryptionKey2": enckey2,
            "prefix": ""}


@pytest.fixture
def device_connection_props_2():
    """ Return connection parameters corresponding to
    device_factory_valid_input_2.
    """
    return {"address": "10.0.0.2:4444",
            "prefix": ""}


@pytest.fixture
def device_factory_fields_2(device_factory_defaults, plugin,
                            device_factory_valid_input_2):
    """ Return UI values set up with different valid user input """
    dialog = dict(device_factory_defaults)
    values, _ = plugin.getDeviceFactoryUiValues([])
    dialog.update(values)
    dialog.update(device_factory_valid_input_2)
    return dialog


@pytest.fixture
def invalid_device_factory_fields(device_factory_defaults):
    """Returns two things: a dictionary set up for the device factory ui
    with invalid user input, and a list of the keys which should be
    marked as errors.
    """
    invalid_values = dict(device_factory_defaults)
    invalid_input = {"portNumber": "not a port",
                     "hiddenencryptionKey1": "not an encryption key",
                     "hiddenencryptionKey2": "still not an encryption key"}
    invalid_values.update(invalid_input)

    return invalid_values, invalid_input.keys()

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
def device_factory_flags():
    """ Initial state of flags in the Device factory dialog. this
    should really read from the xmls instead """
    return {"isConnected": False,
            "error": False,
            "connectionError": False,
            "ipAddressError": False,
            "portNumberError": False,
            "encryptionKey1Error": False,
            "encryptionKey2Error": False}


@pytest.fixture
def device_factory_fields(device_factory_flags):
    """ Return some valid fields for the device factory dialog """
    values = {"ipAddress": "192.168.1.42",
              "portNumber": "4444",
              "encryptionKey1": "01-23-45-67-89-AB-CD-EF",
              "encryptionKey2": "01-23-45-67-89-AB-CD-EF",
              "prefix": ""}
    values.update(device_factory_flags)
    return values


@pytest.fixture
def device_factory_fields_2(device_factory_flags):
    """ Return some different valid fields for the device factory dialog """
    values2 = {"ipAddress": "10.0.0.2",
               "portNumber": "4444",
               "encryptionKey1": "01-23-45-67-89-AB-CD-EF",
               "encryptionKey2": "01-23-45-67-89-AB-CD-EF",
               "prefix": ""}
    values2.update(device_factory_flags)
    return values2


@pytest.fixture
def invalid_device_factory_fields(device_factory_fields):
    """Returns two things: a dictionary set up for the device factory ui
    with invalid user input, and a list of the keys which should be
    marked as errors.
    """
    values = dict(device_factory_fields)
    invalid_values = {"ipAddress": "not an ip address",
                      "portNumber": "not a port",
                      "encryptionKey1": "not an encryption key",
                      "encryptionKey2": "still not an encryption key"}
    values.update(invalid_values)
    return values, invalid_values.keys()

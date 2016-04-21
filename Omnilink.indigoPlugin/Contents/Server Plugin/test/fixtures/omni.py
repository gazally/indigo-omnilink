#! /usr/bin/env python
# Unit tests for Indigo Omni Link plugin
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
""" omni.py: test fixtures to simulate talking to an Omni controller
via the jomnilinkII library. """
from __future__ import print_function
from __future__ import unicode_literals
import itertools

from mock import Mock
import jomnilinkII as jomni_mimic
import pytest


@pytest.fixture
def jomnilinkII(gateway, omnis, jomnilinkII_message):
    """ Return a mock for jomnilinkII """
    jomnilinkII = gateway.jvm.com.digitaldan.jomnilinkII
    jomnilinkII.Connection.side_effect = omnis
    jomnilinkII.Message = jomnilinkII_message
    return jomnilinkII


@pytest.fixture()
def jomnilinkII_message():
    """ return the mock of jomnilinkII.Message. This is used in the
    construction of omnis which is why the jomnilinkII fixture can't
    be used.
    """
    return Mock()


def connection_mock(messages):
    """ Return a mock to be a return value from jomnilinkII.Connection. """

    class CallerBacker(object):
        """Keeps a list of objects and provides a callback method to call
        a named method in each object in its list.
        """
        def __init__(self, names):
            self.callbacks = []
            self.names = names

        def add(self, callback):
            self.callbacks.append(callback)

        def __call__(self, method_name, *args):
            assert method_name in self.names
            [getattr(cb, method_name)(*args) for cb in self.callbacks]

    cm = Mock()
    for name, attribute, obj in messages:
        m = Mock(**{attribute: obj})
        setattr(cm, name, m)

    cm._notify = CallerBacker(["objectStausNotification",
                               "otherEventNotification"])
    cm._disconnect = CallerBacker(["notConnectedEvent"])
    cm.addNotificationListener.side_effect = cm._notify.add
    cm.addDisconnectListener.side_effect = cm._disconnect.add
    return cm


@pytest.fixture
def omnis(omni_messages, omni_messages_2):
    """ List of return values from jomnilinkII.Connection """
    return [connection_mock(omni_messages),
            connection_mock(omni_messages_2)]


@pytest.fixture
def omni1(omnis):
    """ Return the same object that will be returned from the first call to
    jomnilinkII.Connection.
    """
    return omnis[0]


@pytest.fixture
def omni2(omnis):
    """ Return the same object that will be returned from the first call to
    jomnilinkII.Connection.
    """
    return omnis[1]


@pytest.fixture
def req_object_properties(omni_zone_props, omni_unit_props, omni_area_props,
                          omni_end_of_data, jomnilinkII_message):
    """ Return a stand-in for jomnilinkII.Connection.reqObjectProperties """

    zones = itertools.cycle(omni_zone_props + [omni_end_of_data])
    units = itertools.cycle(omni_unit_props + [omni_end_of_data])
    areas = itertools.cycle(omni_area_props + [omni_end_of_data])
    other = itertools.cycle(
        [jomni_mimic.ObjectProperties(Mock(), "test", 1,
                                      jomnilinkII_message.MESG_TYPE_OBJ_PROP),
         omni_end_of_data])

    def reqfunc(mtype, a, b, c, d, e):
        if mtype == jomnilinkII_message.OBJ_TYPE_ZONE:
            return next(zones)
        elif mtype == jomnilinkII_message.OBJ_TYPE_UNIT:
            return next(units)
        elif mtype == jomnilinkII_message.OBJ_TYPE_AREA:
            return next(areas)
        else:
            return next(other)

    return reqfunc


@pytest.fixture
def req_object_status(jomnilinkII_message, omni_unit_statuses,
                      omni_area_statuses):
    """ Return a stand-in for jomnilinkII.Connection.reqObjectStatus. """
    unit_statuses = itertools.cycle(omni_unit_statuses)
    area_statuses = itertools.cycle(omni_area_statuses)

    def reqfunc(mtype, x, y):
        if mtype == jomnilinkII_message.OBJ_TYPE_ZONE:
            return jomni_mimic.ObjectStatus(
                jomnilinkII_message.OBJ_TYPE_ZONE,
                [jomni_mimic.ZoneStatus(0, 0, 100)])

        elif mtype == jomnilinkII_message.OBJ_TYPE_UNIT:
            return next(unit_statuses)
        elif mtype == jomnilinkII_message.OBJ_TYPE_AREA:
            return next(area_statuses)
        else:
            return jomni_mimic.ObjectStatus(Mock(), [Mock()])
    return reqfunc


@pytest.fixture(scope="session")
def req_object_status_zone_states():
    """ return a dictionary containing the device states that match the
    omni_messages fixture """
    return {"sensorValue": 100,
            "onOffState": True,
            "condition": "Secure",
            "alarmStatus": "Secure",
            "armingStatus": "Disarmed",
            "hadTrouble": False}


@pytest.fixture(scope="session")
def req_object_status_unit_states():
    """ Return a dictionary containing the device states that match the
    omni_messages fixture. """
    return {"onOffState": False,
            "brightnessLevel": 0,
            "timeLeftSeconds": 0}


@pytest.fixture
def omni_messages(req_object_properties, req_object_status):
    """ return tuples with mock-building instructions:
    ("name", either "return_value" or "side_effect", value)
    """
    return (("reqSystemInformation", "return_value",
             jomni_mimic.SystemInformation(
                 30,   # model number
                 2,    # firmware version
                 16,   # firmware minor vers
                 2,    # firmware revision
                 "")),  # local phone number
            ("reqSystemStatus", "return_value",
             jomni_mimic.SystemStatus(200,     # battery_reading
                                      16, 2, 14, 11, 13, 14,  # time
                                      5, 30,   # sunrise
                                      18, 30,  # sunset
                                      3,       # day of week
                                      {2: 3},   # alarms
                                      True,  # valid time data
                                      False)),  # daylight savings time
            ("reqSystemTroubles", "return_value",
            # Freeze, Battery Low, AC Power, Phone Line
             jomni_mimic.SystemTroubles([1, 2, 3, 4])),
            ("reqObjectProperties", "side_effect",
             req_object_properties),
            ("reqObjectStatus", "side_effect",
             req_object_status))


def omni1_system_messages_asserts(dev):
    """ assert that controller device states match omni_messages fixture """
    assert dev.states["connected"]
    assert dev.states["model"] == "HAI Omni IIe"
    assert dev.states["firmwareVersion"] == "2.16b"
    assert dev.states["batteryReading"] == 200
    troubles = {"freezeTrouble": True,
                "batteryLowTrouble": True,
                "ACPowerTrouble": True,
                "phoneLineTrouble": True,
                "digitalCommunicatorTrouble": False,
                "fuseTrouble": False}
    for t, val in troubles.items():
        assert dev.states[t] == val


@pytest.fixture
def omni_messages_2(req_object_properties, req_object_status):
    """ return tuples with mock-building instructions:
    ("name", either "return_value" or "side_effect", value)
    """
    return (("reqSystemInformation", "return_value",
             jomni_mimic.SystemInformation(
                 37,   # model number
                 3,    # firmware version
                 0,    # firmware minor vers
                 254,  # firmware revision
                 "")),   # local phone number
            ("reqSystemStatus", "return_value",
             jomni_mimic.SystemStatus(0,        # battery_reading
                                      0, 0, 0, 0, 0, 0,
                                      0, 0,
                                      0, 0,     # time data
                                      0,         # day of week
                                      {1: 1},    # alarms
                                      False,    # valid time data
                                      False)),  # daylight savings
            ("reqSystemTroubles", "return_value",
            # digital communicator, fuse
             jomni_mimic.SystemTroubles([5, 6])),
            ("reqObjectProperties", "side_effect",
             req_object_properties),
            ("reqObjectStatus", "side_effect",
             req_object_status))


def omni2_system_messages_asserts(dev):
    """ assert that controller device states match omni_messages_2 fixture """
    assert dev.states["connected"]
    assert dev.states["model"] == "HAI Lumina Pro"
    assert dev.states["firmwareVersion"] == "3.0X2"
    assert dev.states["batteryReading"] == 0

    troubles = {"freezeTrouble": False,
                "batteryLowTrouble": False,
                "ACPowerTrouble": False,
                "phoneLineTrouble": False,
                "digitalCommunicatorTrouble": True,
                "fuseTrouble": True}
    for t, val in troubles.items():
        assert dev.states[t] == val


@pytest.fixture
def omni_zone_props(jomnilinkII_message):
    """ Return a list of three different ZoneProperties messages. """
    mtype_prop = jomnilinkII_message.MESG_TYPE_OBJ_PROP

    return [jomni_mimic.ZoneProperties(mtype_prop, "Front Door", 1, 1, 1, 0),
            jomni_mimic.ZoneProperties(mtype_prop, "Motion", 2, 3, 1, 1),
            jomni_mimic.ZoneProperties(mtype_prop, "Smoke Det", 3, 32, 1, 3)]


@pytest.fixture(scope="session")
def req_object_props_zone_states():
    """ Return a dictionary containing the device states that match
    the omni_zone_props fixture.
    """
    return {"Front Door": {"name": "Front Door",
                           "type": "Perimeter",
                           "area": 1,
                           "crossZoning": False,
                           "swingerShutdown": False,
                           "dialOutDelay": False},
            "Motion": {"name": "Motion",
                       "type": "Away Interior",
                       "area": 1,
                       "crossZoning": True,
                       "swingerShutdown": False,
                       "dialOutDelay": False},
            "Smoke Det": {"name": "Smoke Det",
                          "type": "Fire",
                          "area": 1,
                          "crossZoning": True,
                          "swingerShutdown": True,
                          "dialOutDelay": False}}


@pytest.fixture
def omni_end_of_data(jomnilinkII_message):
    return jomni_mimic.EndOfData(jomnilinkII_message.MESG_TYPE_END_OF_DATA)


@pytest.fixture
def omni_unit_props(jomnilinkII_message):
    mtype = jomnilinkII_message.MESG_TYPE_OBJ_PROP
    return [jomni_mimic.UnitProperties(mtype, "X10 Unit", 1, 1),
            jomni_mimic.UnitProperties(mtype, "Radio RA", 2, 8),
            jomni_mimic.UnitProperties(mtype, "Voltage", 3, 13)]


@pytest.fixture
def omni_unit_statuses(jomnilinkII_message):
    return [jomni_mimic.ObjectStatus(jomnilinkII_message.OBJ_TYPE_UNIT,
                                     [jomni_mimic.UnitStatus(0, 0, 0)]),
            jomni_mimic.ObjectStatus(jomnilinkII_message.OBJ_TYPE_UNIT,
                                     [jomni_mimic.UnitStatus(0, 25, 30)]),
            jomni_mimic.ObjectStatus(jomnilinkII_message.OBJ_TYPE_UNIT,
                                     [jomni_mimic.UnitStatus(0, 37, 30)]),
            jomni_mimic.ObjectStatus(jomnilinkII_message.OBJ_TYPE_UNIT,
                                     [jomni_mimic.UnitStatus(0, 150, 45)]),
            jomni_mimic.ObjectStatus(jomnilinkII_message.OBJ_TYPE_UNIT,
                                     [jomni_mimic.UnitStatus(0, 250, 30)])]


@pytest.fixture(scope="session")
def omni_unit_types():
    """ Return a list of the device types corresponding to omni_unit_props. """
    return ["omniStandardUnit", "omniRadioRAUnit", "omniVoltageUnit"]

@pytest.fixture
def omni_area_props(jomnilinkII_message):
    mtype = jomnilinkII_message.MESG_TYPE_OBJ_PROP
    return [jomni_mimic.AreaProperties(mtype, "First Area", 1, 10, 20, True),
            jomni_mimic.AreaProperties(mtype, "", 2, 30, 40, True),
            jomni_mimic.AreaProperties(mtype, "", 3, 0, 0, False)]


@pytest.fixture(scope="session")
def req_object_props_area_states():
    """ Return a dictionary containing the device states that match
    the omni_area_props fixture.
    """
    return {"First Area": {"name": "First Area",
                           "entryDelay": 10,
                           "exitDelay": 20},
            "Area 2": {"name": "Area 2",
                       "entryDelay": 30,
                       "exitDelay": 40}}


@pytest.fixture
def omni_area_statuses(jomnilinkII_message):
    return [jomni_mimic.ObjectStatus(jomnilinkII_message.OBJ_TYPE_AREA,
                                     [jomni_mimic.AreaStatus(1, 0, 6, 0, 0)]),
            jomni_mimic.ObjectStatus(jomnilinkII_message.OBJ_TYPE_AREA,
                                     [jomni_mimic.AreaStatus(2, 12, 0, 10, 10)]),
            jomni_mimic.ObjectStatus(jomnilinkII_message.OBJ_TYPE_AREA,
                                     [jomni_mimic.AreaStatus(3, 2, 0, 0, 0)])]

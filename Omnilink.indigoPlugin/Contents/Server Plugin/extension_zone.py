#! /usr/bin/env python
# A plugin for Indigo Server to communicate with HAI/Leviton OMNI systems
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

""" Omni Plugin extension for Zones """
from __future__ import unicode_literals

from distutils.version import StrictVersion
import logging

import indigo
from py4j.protocol import Py4JError

import extensions
from connection import ConnectionError

log = logging.getLogger(__name__)

_VERSION = "0.3.0"


class ZoneExtension(extensions.DeviceMixin, extensions.PluginExtension):
    """Omni plugin extension for Zones """
    def __init__(self):
        self.type_ids = {"device": ["omniZoneDevice"],
                         "action": [],
                         "event": []}
        self.callbacks = {}

        extensions.DeviceMixin.__init__(self, ZoneInfo, log)

    # ----- Device updates ----- #

    def update_device_version(self, device):
        """ if the device was defined in a previous version of this plugin,
        update it and change the version number. Note that
        replacePluginPropsOnServer calls deviceStartComm, so it's important
        to avoid calling it if nothing needs to be changed.
        """
        device_version = device.pluginProps.get("deviceVersion", "0.0")
        if (StrictVersion(device_version) >= StrictVersion(_VERSION)):
            return
        if StrictVersion(device_version) < StrictVersion("0.3.0"):
            raise extensions.OldVersionError

    def update_device_from_status(self, dev, status):
        extensions.DeviceMixin.update_device_from_status(self, dev, status)
        dev.updateStateOnServer("sensorValue", status.loop,
                                uiValue=str(status.loop))

    # ----- Device creation methods ----- #

    def createDevices(self, dev_type, values, prefix, dev_ids):
        """Automatically create a device for each zone, unless it already
        exists. Values should contain properties for the devices and
        prefix shoudl contain a string used to prefix unique names for the
        devices. On return values will contain additional props used
        to create the devices.

        """
        values["SupportsOnState"] = True
        values["SupportsSensorValue"] = True
        values["SupportsStatusRequest"] = True
        extensions.DeviceMixin.createDevices(self, dev_type, values, prefix,
                                             dev_ids)

    # ----- Callbacks from Indigo for device actions ----- #

    def actionControlSensor(self, action, dev):
        """ Callback from Indigo for commands to change the sensor state.
        Not supported by Omni Zone sensors. And it's not documented, but
        sometimes RequestStatus gets sent here, sometimes it gets sent
        to actionControlGeneral.
        """
        if action.sensorAction == indigo.kSensorAction.RequestStatus:
            indigo.server.log("sending status request to " + dev.name)
            self.update_device_status(dev)
            return

        log.error('ignored "{0}" request: sensor "{1}" is read-only'.format(
            action.sensorAction.name, dev.name))

    def actionControlGeneral(self, action, dev):
        """ Callback from Indigo for some general device actions """
        if action.deviceAction == indigo.kDeviceGeneralAction.RequestStatus:
            indigo.server.log("sending status request to " + dev.name)
            self.update_device_status(dev)
            return

        log.error('ignored "{0}" request: action not implemented for '
                  'sensor "{1}"'.format(action.deviceAction.name, dev.name))


class ZoneInfo(extensions.Info):
    """ Get the zone info from the Omni device, and assist
    in fetching status and deciphering notification events for zones.

    Public methods:
        number_and_status_from_notification: return name of zone and ZoneStatus
            object deciphered from Omni event notification method
        fetch_status: query Omni for zone status for a zone
        fetch_props: return a ZoneProperties object for one zone
        report: given a print method, write formatted info about all zones
    """
    reports = ["Zones"]

    def __init__(self, connection):
        """ ZoneInfo constructor
        Parameter:
            connection -- any ducktyped object that provides:
                connection.jomnilinkII - link to jomnilinkII java library
                                          via py4j
                connection.omni - a Connection object from jomnilinkII

        May raise Py4JError or ConnectionError
        """
        self.connection = connection
        self.props = self.fetch_all_props(connection, ZoneProperties, "ZONE",
                                          "NAMED", "AREA_ALL", "ANY_LOAD")
        log.debug("Zones defined on Omni system: " +
                  ", ".join((zp.name for num, zp in self.props.items())))

    def fetch_status(self, objnum):
        """Given the number of a zone query the Omni controller for the
        current status of the zone and return a ZoneStatus object.
        May raise ConnectionError or Py4JavaError if there is no valid
        connection or a network error.
        """
        if objnum not in self.props:
            raise ConnectionError("Zone {0} is not defined on Omni system")
        jomnilinkII = self.connection.jomnilinkII
        Message = jomnilinkII.Message
        status_msg = self.connection.omni.reqObjectStatus(
            Message.OBJ_TYPE_ZONE, objnum, objnum)
        status = status_msg.getStatuses()[0]
        return ZoneStatus(status)

    def number_and_status_from_notification(self, status_msg):
        """ Given a status message from the JomniLinkII notification
        listener, determine if it is about a zone. If it is, return the
        number of the zone and a ZoneStatus object, otherwise return
        (None, None)
        """
        Message = self.connection.jomnilinkII.Message
        if status_msg.getStatusType() != Message.OBJ_TYPE_ZONE:
            return None, None

        statuses = status_msg.getStatuses()
        status = statuses[0]
        objnum = status.getNumber()
        log.debug("Received status for " + self.props[objnum].name)

        return objnum, ZoneStatus(status)

    def report(self, report_name, say):
        items = sorted(self.props.items())
        if not items:
            say("None")
            return
        widths = [("Num", 3),
                  ("Name", 15),
                  ("Type", 27),
                  ("Area", 4),
                  ("Options", 9),
                  ("Loop", 4),
                  ("Condition", 9),
                  ("Latched", 7),
                  ("Arming", 13),
                  ("Trouble", 11)]

        fmt = "  ".join(("{{{0}: <{1}}}".format(i, w[1]) for i, w in
                         enumerate(widths)))
        say(fmt.format(*(n for n, w in widths)))
        for num, zp in items:
            options = "CZ " if zp.cross_zoning else ""
            if zp.swinger_shutdown:
                options = options + "SS "
            if zp.dial_out_delay:
                options = options + "DOD"

            zs = self.fetch_status(num)
            trouble = "Had Trouble" if zs.had_trouble else "None"

            say(fmt.format(num, zp.name, zp.type_name, zp.area, options,
                           zs.loop, zs.condition, zs.latched_alarm, zs.arming,
                           trouble))
        say("Abbreviations: CZ: Cross Zoning, SS: Swinger Shutdown, "
            "DOD: Dial out Delay")


class ZoneProperties(extensions.Props):
    """ ZoneProperties class, represents Omni zone properties """
    def __init__(self, omni_props):
        """ Construct a ZoneProperties object from the jomnilinkII
        Zone Properties object.
        """
        self.device_type = "omniZoneDevice"
        self.type_name = "Zone"

        self.name = omni_props.getName()
        self.number = omni_props.getNumber()
        zone_type = omni_props.getZoneType()
        self.zone_type = self.zone_types.get(
            zone_type, "Unknown Zone Type {0}".format(zone_type))
        self.area = omni_props.getArea()

        options = omni_props.getOptions()
        self.cross_zoning = (0b01 & options) != 0
        self.swinger_shutdown = (0b010 & options) != 0
        self.dial_out_delay = (0b0100 & options) != 0

    def device_states(self):
        return {"name": self.name,
                "crossZoning": self.cross_zoning,
                "swingerShutdown": self.swinger_shutdown,
                "dialOutDelay": self.dial_out_delay,
                "type": self.zone_type,
                "area": self.area}

    zone_types = {0: "Entry/Exit",
                  1: "Perimeter",
                  2: "Night Interior",
                  3: "Away Interior",
                  4: "Double Entry Delay",
                  5: "Quadruple Entry Delay",
                  6: "Latching Perimeter",
                  7: "Latching Night Interior",
                  8: "Latching Away Interior",
                  16: "Panic",
                  17: "Police Emergency",
                  18: "Duress",
                  19: "Tamper",
                  20: "Latching Tamper",
                  32: "Fire",
                  33: "Fire Emergency",
                  34: "Gas Alarm",
                  48: "Auxiliary Emergency",
                  49: "Trouble",
                  54: "Freeze",
                  55: "Water",
                  56: "Fire Tamper",
                  64: "Auxiliary",
                  65: "Keyswitch Input",
                  80: "Program Energy Saver Module",
                  81: "Outdoor Temperature",
                  82: "Temperature",
                  83: "Temperature Alarm",
                  84: "Humidity",
                  85: "Extended Range Outdoor Temp",
                  85: "Extended Range Temp",
                  85: "Extended Range Temp Alarm"
                  }


class ZoneStatus(extensions.Status):
    """ ZoneStatus class, represents Omni Zone status """
    def __init__(self, omni_status):
        """ Construct a ZoneStatus object from a jomnilinkII
        Zone Status object. """
        status_byte = omni_status.getStatus()
        self.loop = omni_status.getLoop()

        self.condition = self.conditions[status_byte &
                                         self.condition_mask]
        self.latched_alarm = self.latched_alarms[status_byte &
                                                 self.latched_alarm_mask]
        self.arming = self.armings[status_byte &
                                   self.arming_mask]
        self.had_trouble = (status_byte & self.trouble_mask) != 0

    def device_states(self):
        return {"condition": self.condition,
                "onOffState": self.condition == "Secure",
                "alarmStatus": self.latched_alarm,
                "armingStatus": self.arming,
                "hadTrouble": self.had_trouble,
                "sensorValue": self.loop}

    conditions = {0b00: "Secure",
                  0b01: "Not Ready",
                  0b10: "Trouble",
                  0b11: "Undefined"}
    condition_mask = 0b11

    latched_alarms = {0b0000: "Secure",
                      0b0100: "Tripped",
                      0b1000: "Reset",
                      0b1100: "Undefined"}
    latched_alarm_mask = 0b1100

    armings = {0b000000: "Disarmed",
               0b010000: "Armed",
               0b100000: "User Bypass",
               0b110000: "System Bypass"}
    arming_mask = 0b110000

    trouble_mask = 0b1000000

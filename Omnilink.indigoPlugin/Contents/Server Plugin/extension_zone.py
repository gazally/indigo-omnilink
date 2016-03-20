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
import logging

import indigo
from py4j.protocol import Py4JError

import extensions
from extensions import ConnectionError

log = logging.getLogger(__name__)

_VERSION = "0.1.0"


class ZoneExtension(extensions.PluginExtension):
    """Omni plugin extension for Zones """
    def __init__(self):
        self.type_ids = {"device": ["omniZoneDevice"],
                         "action": [],
                         "event": []}
        self.devices = []
        self._zone_info = {}
        self.callbacks = {}

    # ----- Device Start and Stop Methods ----- #

    def deviceStartComm(self, device):
        """ Start an omniZoneDevice. Query the Omni system and set the status
        of the indigo device """

        if device not in self.devices:
            self.devices.append(device)

        self.update_device_status(device)

    def deviceStopComm(self, device):
        if device in self.devices:
            self.devices.remove(device)

    # ----- Device creation methods ----- #

    def getDeviceList(self, props, dev_ids):
        """ Query the Omni controller to see if any zones are defined.
        If there are, return omniZoneDevice as the device type we can create.
        Otherwise, return an empty list.
        """
        result = []
        try:
            if self.zone_info(props).zone_props:
                result = [("omniZoneDevice", "Zone")]
        except (Py4JError, ConnectionError):
            log.error("Failed to fetch zone information from Omni Controller")
            log.debug("", exc_info=True)
        return result

    def createDevices(self, values, prefix, dev_ids):
        """ Automatically create a device for each zone, unless it already
        exists. """
        old_devs = [
            indigo.devices[id] for id in dev_ids
            if indigo.devices[id].deviceTypeId == "omniZoneDevice"]
        values["deviceVersion"] = _VERSION
        try:
            for zp in self.zone_info(values).zone_props.values():
                if not any((dev.pluginProps["number"] == zp.number
                            for dev in old_devs)):
                    self.create_device(zp, values, prefix)
        except (Py4JError, ConnectionError):
            log.error("Failed to fetch zone information from Omni Controller")
            log.debug("", exc_info=True)

    def create_device(self, zone_props, values, prefix):
        """ Create a new device, given zone properties and device properties
        """
        log.debug("Creating Zone device for {0}:{1}".format(zone_props.number,
                                                            zone_props.name))
        values["number"] = zone_props.number
        kwargs = {"props": values,
                  "deviceTypeId": "omniZoneDevice"}
        name = self.get_unique_name(prefix, zone_props.name)
        if name:
            kwargs["name"] = name
        newdev = indigo.device.create(indigo.kProtocol.Plugin, **kwargs)
        newdev.model = self.MODEL
        newdev.subModel = "Zone"
        newdev.replaceOnServer()

    # ----- Callbacks from OMNI Status and events ----- #

    def status_notification(self, connection, status_msg):
        connection_props = self.plugin.props_from_connection(connection)
        zone_info = self.zone_info(connection_props)
        number = None
        try:
            number, status = zone_info.number_and_status_from_notification(
                status_msg)
        except Py4JError, ConnectionError:
            log.debug("status_notification exception in Zone", exc_info=True)

        if number is None:
            return
        for dev in self.devices:
            if dev.pluginProps["number"] == number:
                self.update_device_from_status(dev, status)

    def reconnect_notification(self, connection):
        connection_key = self.plugin.make_connection_key(
            self.plugin.props_from_connection(connection))
        for dev in self.devices:
            if (self.plugin.make_connection_key(dev.pluginProps) ==
                    connection_key):
                self.update_device_status(dev)

    def disconnect_notification(self, connection, e):
        connection_key = self.plugin.make_connection_key(
            self.plugin.props_from_connection(connection))
        for dev in self.devices:
            if (self.plugin.make_connection_key(dev.pluginProps) ==
                    connection_key):
                dev.setErrorStateOnServer("not connected")

    def update_device_status(self, dev):
        try:
            zone_info = self.zone_info(dev.pluginProps)
            props = zone_info.zone_props[dev.pluginProps["number"]]
            status = zone_info.fetch_status(dev.pluginProps["number"])
        except (ConnectionError, Py4JError):
            log.error("Failed to get status of zone {0} from Omni".format(
                dev.pluginProps["number"]))
            dev.setErrorStateOnServer("not connected")
            return

        dev.updateStateOnServer("name", props.name)
        dev.updateStateOnServer("crossZoning", props.cross_zoning)
        dev.updateStateOnServer("swingerShutdown", props.swinger_shutdown)
        dev.updateStateOnServer("dialOutDelay", props.dial_out_delay)
        dev.updateStateOnServer("type", props.type_name)
        dev.updateStateOnServer("area", props.area)
        self.update_device_from_status(dev, status)
        dev.setErrorStateOnServer(None)

    def update_device_from_status(self, dev, status):
        dev.updateStateOnServer("condition", status.condition)
        dev.updateStateOnServer("alarmStatus", status.latched_alarm)
        dev.updateStateOnServer("armingStatus", status.arming)
        dev.updateStateOnServer("hadTrouble", status.had_trouble)
        dev.updateStateOnServer("loop", status.loop)

    def zone_info(self, props):
        key = self.plugin.make_connection_key(props)
        if key not in self._zone_info:
            self._zone_info[key] = ZoneInfo(
                self.plugin.make_connection(props))
        return self._zone_info[key]


class ZoneInfo(object):
    """ Get the zone info from the Omni device, and assist
    in fetching status and deciphering notification events for zones.

    Public methods:
        number_and_status_from_notification: return name of zone and ZoneStatus
            object deciphered from Omni event notification method
        fetch_status: query Omni for zone status for a zone
        fetch_props: return a ZoneProperties object for one zone
    """

    def __init__(self, connection):
        """ ZoneInfo constructor
        Parameter:
            connection -- any ducktyped object that provides:
                connection.is_connected() - return True if an active
                                          connection to Omni
                connection.jomnilinkII - link to jomnilinkII java library
                                          via py4j
                connection.omni - a Connection object from jomnilinkII

        May raise Py4JError or ConnectionError
        """
        self.connection = connection
        self.zone_props = self._fetch_all_props()
        log.debug("Zones defined on Omni system: " +
                  ", ".join((zp.name for num, zp in self.zone_props.items())))

    def _fetch_all_props(self):
        """ Query the connected Omni device for the properties of all the
        named zones. Build ZoneProperties objects out of them, ignoring the
        statuses, and return a dictionary indexed by object number.
        Raises Py4JJavaError or ConnectionError if there is a
        network error """
        Message = self.connection.jomnilinkII.Message
        ObjectProps = self.connection.jomnilinkII.MessageTypes.ObjectProperties
        objnum = 0
        results = {}
        while True:
            m = self.connection.omni.reqObjectProperties(
                Message.OBJ_TYPE_ZONE,
                objnum, 1,
                ObjectProps.FILTER_1_NAMED,
                ObjectProps.FILTER_2_AREA_ALL,
                ObjectProps.FILTER_3_ANY_LOAD)
            if m.getMessageType() != Message.MESG_TYPE_OBJ_PROP:
                break
            objnum = m.getNumber()
            results[objnum] = ZoneProperties(m)
        return results

    def fetch_status(self, objnum):
        """Given the number of a zone query the Omni controller for the
        current status of the zone and return a ZoneStatus object.
        May raise ConnectionError or Py4JavaError if there is no valid
        connection or a network error.
        """
        if objnum not in self.zone_props:
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
        log.debug("Received status for " + self.zone_props[objnum].name)

        return objnum, ZoneStatus(status)


class ZoneProperties(object):
    """ ZoneProperties class, represents Omni zone properties """
    def __init__(self, omni_props):
        """ Construct a ZoneProperties object from the jomnilinkII
        Zone Properties object.
        """
        self.name = omni_props.getName()
        self.number = omni_props.getNumber()
        zone_type = omni_props.getZoneType()
        self.type_name = self.type_names.get(
            zone_type, "Unknown Zone Type {0}".format(zone_type))
        self.area = omni_props.getArea()

        options = omni_props.getOptions()
        self.cross_zoning = (0b01 & options) != 0
        self.swinger_shutdown = (0b010 & options) != 0
        self.dial_out_delay = (0b0100 & options) != 0

    type_names = {0: "Entry/Exit",
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
                  80: "Programmable Energy Saver Module",
                  81: "Outdoor Temperature",
                  82: "Temperature",
                  83: "Temperature Alarm",
                  84: "Humidity",
                  85: "Extended Range Outdoor Temperature",
                  85: "Extended Range Temperature",
                  85: "Extended Range Temperature Alarm"
                  }


class ZoneStatus(object):
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
               0b100000: "Bypassed by User",
               0b110000: "Bypassed by System"}
    arming_mask = 0b110000

    trouble_mask = 0b1000000

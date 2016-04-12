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

""" Omni Plugin extension for Control Units """
from __future__ import unicode_literals
from collections import defaultdict
import logging

import indigo
from py4j.protocol import Py4JError

import extensions
import connection
from connection import ConnectionError

log = logging.getLogger(__name__)

_VERSION = "0.1.0"


class ControlUnitExtension(extensions.PluginExtension):
    """Omni plugin extension for Control Units """
    device_types = {
        1: ("omniStandardX10Unit",  "Standard X10 Control"),
        2: ("omniExtendedX10Unit",  "Extended X10 Control"),
        3: ("omniComposeX10Unit",   "Compose X10 Control"),
        4: ("omniUPBUnit",          "UPB Control"),
        5: ("omniHLCRoomUnit",      "HLC Room Control"),
        6: ("omniHLCLoadUnit",      "HLC Load Control"),
        7: ("omniLuminaModeUnit",   "Lumina Mode Control"),
        8: ("omniRadioRAUnit",      "Radio RA Control"),
        9: ("omniCentraLiteUnit",   "CentraLite Control"),
        10: ("omniViziaRFRoomUnit", "Vizia RF Room Control"),
        11: ("omniViziaRFLoadUnit", "Vizia RF Load Control"),
        12: ("omniFlagUnit",        "Omni Controller Flag"),
        13: ("omniVoltageUnit",     "Voltage Output Control"),
        14: ("omniAudioZoneUnit",   "Audio Zone Control"),
        15: ("omniAudioSourceUnit", "Audio Source Control"),
    }
    relay_device_types = ["omniFlagUnit", "omniVoltageUnit",
                          "omniAudioZoneUnit", "omniAudioSourceUnit"]

    def __init__(self):
        self.type_ids = {"action": [],
                         "event": []}
        self.type_ids["device"] = [devtype for devtype, name
                                   in self.device_types.values()]
        self.callbacks = {}
        self.reports = {"Control Units": self.say_unit_info}

        # key is device type, list contains device id's
        self.device_ids = defaultdict(list)

        # key is url, list is UnitInfo instances
        self._unit_info = {}

    # ----- Device Start and Stop Methods ----- #

    def deviceStartComm(self, device):
        """Start one of the control unit devices. Query the Omni system and
        set the status of the indigo device.
        """
        log.debug('Starting device "{0}"'.format(device.name))
        if device.id not in self.device_ids[device.deviceTypeId]:
            self.device_ids[device.deviceTypeId].append(device.id)

        self.update_device_status(device)

    def deviceStopComm(self, device):
        if device.id in self.device_ids[device.deviceTypeId]:
            log.debug('Stopping device "{0}"'.format(device.name))
            self.device_ids[device.deviceTypeId].remove(device.id)

    # ----- Device creation methods ----- #

    def getDeviceList(self, url, dev_ids):
        """ Query the Omni controller to see if any units are defined.
        If there are, return the device types found.
        Otherwise, return an empty list.
        """
        result = []
        try:
            unit_props = self.unit_info(url).unit_props
            result = list(set(((up.device_type, up.type_name) for up in
                               unit_props.values())))
        except (Py4JError, ConnectionError):
            log.error("Failed to fetch control unit information from the "
                      "Omni Controller")
            log.debug("", exc_info=True)
        return result

    def createDevices(self, dev_type, values, prefix, dev_ids):
        """Automatically create a device for each control unit, unless it
        already exists.
        """
        old_devs = [
            indigo.devices[id] for id in dev_ids
            if indigo.devices[id].deviceTypeId == dev_type]
        values["deviceVersion"] = _VERSION
        try:
            for up in self.unit_info(values["url"]).unit_props.values():
                if up.device_type == dev_type:
                    if not any((dev.pluginProps["number"] == up.number
                                for dev in old_devs)):
                        self.create_device(up, values, prefix)
        except (Py4JError, ConnectionError):
            log.error("Failed to fetch control unit information from the "
                      "Omni Controller")
            log.debug("", exc_info=True)

    def create_device(self, unit_props, values, prefix):
        """Create a new device, given control unit properties and device
        properties.
        """
        log.debug("Creating control unit device type {2} "
                  "for {0}:{1}".format(unit_props.number,
                                       unit_props.name,
                                       unit_props.device_type))
        values["number"] = unit_props.number
        kwargs = {"props": values,
                  "deviceTypeId": unit_props.device_type}
        name = self.get_unique_name(prefix, unit_props.name)
        if name:
            kwargs["name"] = name
        newdev = indigo.device.create(indigo.kProtocol.Plugin, **kwargs)
        newdev.model = self.MODEL
        newdev.subModel = unit_props.type_name
        newdev.replaceOnServer()

    # ----- Device Action Callbacks ----- #

    def actionControlDimmerRelay(self, action, dev):
        """ Callback from Indigo Server to implement actions for dimmer and
        relay devices.
        """
        k = indigo.kDimmerRelayAction
        dispatch = {k.TurnOn:        (self.turn_on,        "on"),
                    k.TurnOff:       (self.turn_off,       "off"),
                    k.Toggle:        (self.toggle,         "toggle"),
                    k.SetBrightness: (self.set_brightness, "set-brightness"),
                    k.BrightenBy:    (self.brighten_by,    "brighten-by"),
                    k.DimBy:         (self.dim_by,         "dim-by")
                    }

        method, text = dispatch[action.deviceAction]
        try:
            unit_num = dev.pluginProps["number"]
            unit_info = self.unit_info(dev.pluginProps["url"])
            method(action, dev, unit_num, unit_info)
            indigo.server.log('sent "{0}" {1} request'.format(dev.name, text))
        except Py4JError, ConnectionError:
            log.error('send "{0}" {1} request failed'.format(dev.name, text))
            log.debug("", exc_info=True)

    def turn_on(self, action, dev, unit_num, unit_info):
        unit_info.send_command("CMD_UNIT_ON", unit_num, 0)

    def turn_off(self, action, dev, unit_num, unit_info):
        unit_info.send_command("CMD_UNIT_OFF", unit_num, 0)

    def toggle(self, action, dev, unit_num, unit_info):
        if dev.onState:
            self.turn_off(action, dev, unit_num, unit_info)
        else:
            self.turn_on(action, dev, unit_num, unit_info)

    def set_brightness(self, action, dev, unit_num, unit_info):
        unit_info.send_command("CMD_UNIT_PERCENT", unit_num,
                               action.actionValue)

    def brighten_by(self, action, dev, unit_num, unit_info):
        new_level = min(100, dev.brightness + action.actionValue)
        unit_info.send_command("CMD_UNIT_PERCENT", unit_num, new_level)

    def dim_by(self, action, dev, unit_num, unit_info):
        new_level = max(0, dev.brightness - action.actionValue)
        unit_info.send_command("CMD_UNIT_PERCENT", unit_num, new_level)

    def actionControlGeneral(self, action, dev):
        """ Callback from Indigo Server to implement general device actions.
        The only one that makes sense with Omni units is RequestStatus.
        """
        if action.deviceAction == indigo.kDeviceGeneralAction.RequestStatus:
            indigo.server.log("sending status update request to {0}".format(
                dev.name))
            self.update_device_status(dev)
            return
        log.error("Device action {0} is not implemented for {1}".format(
            action.deviceAction.name, dev.name))

    # ----- Callbacks from OMNI Status and events ----- #

    def status_notification(self, connection, status_msg):
        try:
            if (status_msg.getStatusType() !=
                    connection.jomnilinkII.Message.OBJ_TYPE_UNIT):
                return
            unit_info = self.unit_info(connection.url)
            number, status = unit_info.number_and_status_from_notification(
                status_msg)
        except Py4JError, ConnectionError:
            log.debug("status_notification exception in Unit", exc_info=True)
        else:
            for dev in self.devices_from_url(connection.url):
                if dev.pluginProps["number"] == number:
                    self.update_device_from_status(dev, status)

    def reconnect_notification(self, connection):
        for dev in self.devices_from_url(connection.url):
            self.update_device_status(dev)

    def disconnect_notification(self, connection, e):
        for dev in self.devices_from_url(connection.url):
            dev.setErrorStateOnServer("disconnected")

    def devices_from_url(self, url):
        """ Produce an iteration of device objects matching the given url
        by selecting from self.device_ids """
        for dev_ids_of_type in self.device_ids.values():
            for dev_id in dev_ids_of_type:
                dev = indigo.devices[dev_id]
                if (url == dev.pluginProps["url"]):
                    yield dev

    def update_device_status(self, dev):
        unit_num = dev.pluginProps["number"]
        try:
            unit_info = self.unit_info(dev.pluginProps["url"])
            props = unit_info.unit_props[unit_num]
            status = unit_info.fetch_status(unit_num)
        except (ConnectionError, Py4JError):
            log.debug("Failed to get status of unit {0} from Omni".format(
                unit_num))
            dev.setErrorStateOnServer("disconnected")
            return

        dev.updateStateOnServer("name", props.name)
        self.update_device_from_status(dev, status)
        dev.setErrorStateOnServer(None)

    def update_device_from_status(self, dev, status):
        dev.updateStateOnServer("onOffState", status.status != 0)
        dev.updateStateOnServer("timeLeftSeconds", status.time)
        if dev.deviceTypeId not in self.relay_device_types:
            dev.updateStateOnServer("brightnessLevel", status.status)

    def unit_info(self, url):
        """ Handles caching UnitInfo objects by url. Makes a new one if
        we don't have it yet for that url or if the underlying connection
        object has changed. """
        connection = self.plugin.make_connection(url)
        if (url not in self._unit_info or
                self._unit_info[url].connection is not connection):
            self._unit_info[url] = UnitInfo(connection)

        return self._unit_info[url]

    # ----- Write info on units to log ----- #

    def say_unit_info(self, report, connection, say):
        unit_info = self.unit_info(connection.url)
        unit_info.report(say)


class UnitInfo(object):
    """ Get the unit info from the Omni device, and assist
    in fetching status, deciphering notification events and
    sending commands for units.

    Public methods:
        number_and_status_from_notification: return name of unit and UnitStatus
            object deciphered from Omni event notification method
        fetch_status: query Omni for unit status for a unit
        fetch_props: return a UnitProperties object for one unit
        send_command: send a command
        report: given a print method, write formatted info about all units
    """

    def __init__(self, connection):
        """ UnitInfo constructor
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
        self.unit_props = self._fetch_all_props()
        log.debug("Units defined on Omni system: " +
                  ", ".join((zp.name for num, zp in self.unit_props.items())))

    def _fetch_all_props(self):
        """ Query the connected Omni device for the properties of all the
        named units. Build UnitProperties objects out of them, ignoring the
        statuses, and return a dictionary indexed by object number.
        Raises Py4JJavaError or ConnectionError if there is a
        network error """
        Message = self.connection.jomnilinkII.Message
        ObjectProps = self.connection.jomnilinkII.MessageTypes.ObjectProperties
        objnum = 0
        results = {}
        while True:
            m = self.connection.omni.reqObjectProperties(
                Message.OBJ_TYPE_UNIT,
                objnum, 1,
                ObjectProps.FILTER_1_NAMED,
                ObjectProps.FILTER_2_AREA_ALL,
                ObjectProps.FILTER_3_ANY_LOAD)
            if m.getMessageType() != Message.MESG_TYPE_OBJ_PROP:
                break
            objnum = m.getNumber()
            results[objnum] = UnitProperties(m)
        return results

    def fetch_status(self, objnum):
        """Given the number of a unit query the Omni controller for the
        current status of the unit and return a UnitStatus object.
        May raise ConnectionError or Py4JavaError if there is no valid
        connection or a network error.
        """
        if objnum not in self.unit_props:
            raise ConnectionError("Unit {0} is not defined on Omni system")
        jomnilinkII = self.connection.jomnilinkII
        Message = jomnilinkII.Message
        status_msg = self.connection.omni.reqObjectStatus(
            Message.OBJ_TYPE_UNIT, objnum, objnum)
        status = status_msg.getStatuses()[0]
        return UnitStatus(status)

    def number_and_status_from_notification(self, status_msg):
        """ Given a status message from the JomniLinkII notification
        listener, determine if it is about a unit. If it is, return the
        number of the unit and a UnitStatus object, otherwise return
        (None, None)
        """
        Message = self.connection.jomnilinkII.Message
        if status_msg.getStatusType() != Message.OBJ_TYPE_UNIT:
            return None, None

        statuses = status_msg.getStatuses()
        status = statuses[0]
        objnum = status.getNumber()
        log.debug("Received status for " + self.unit_props[objnum].name)

        return objnum, UnitStatus(status)

    def send_command(self, cmd_name, unit_num, parameter):
        """ Send the Omni controller a command, specified by name,
        along with the unit number and parameter value.
        See comments in jomnilinkII.MessageTypes.CommandMessage
        for details.
        """
        cmd = getattr(self.connection.jomnilinkII.MessageTypes.CommandMessage,
                      cmd_name)
        self.connection.omni.controllerCommand(cmd, unit_num, parameter)

    def report(self, say):
        items = sorted(self.unit_props.items())
        if not items:
            say("None")
            return
        widths = [("Num", 3),
                  ("Name", 12),
                  ("Type", 22),
                  ("Time (seconds)", 14),
                  ("Status", 6)]

        fmt = "  ".join(("{{{0}: <{1}}}".format(i, w[1]) for i, w in
                         enumerate(widths)))
        say(fmt.format(*(n for n, w in widths)))
        for num, up in items:
            us = self.fetch_status(num)
            if us.status == 0:
                status = "Off"
            elif us.status == 1:
                status = "On"
            elif 2 <= us.status <= 13:
                status = "Scene " + chr(ord('A') + us.status - 2)
            elif 17 <= us.status <= 25:
                status = "Dim by " + str(us.status - 16)
            elif 33 <= us.status <= 41:
                status = "Brighten by " + str(us.status - 32)
            elif 100 <= us.status <= 200:
                status = str(us.status - 100) + "%"
            else:
                status = str(status)
            say(fmt.format(num, up.name, up.type_name, us.time, status))


class UnitProperties(object):
    """ UnitProperties class, represents Omni control unit properties """
    def __init__(self, omni_props):
        """ Construct a UnitProperties object from the jomnilinkII
        Unit Properties object.
        """
        self.name = omni_props.getName()
        self.number = omni_props.getNumber()
        unit_type = omni_props.getUnitType()
        self.device_type, self.type_name = \
            ControlUnitExtension.device_types.get(
                unit_type, ("", "Unknown Unit Type {0}".format(unit_type)))


class UnitStatus(object):
    """ UnitStatus class, represents Omni Unit status """
    def __init__(self, omni_status):
        """ Construct a UnitStatus object from a jomnilinkII
        Unit Status object. """
        self.status = omni_status.getStatus()
        self.time = omni_status.getTime()

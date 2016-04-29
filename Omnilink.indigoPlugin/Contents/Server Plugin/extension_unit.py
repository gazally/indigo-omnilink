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
import logging

import indigo
from py4j.protocol import Py4JError

import extensions
from connection import ConnectionError
from properties import UnitProperties, UnitStatus

log = logging.getLogger(__name__)

_VERSION = "0.3.0"


class ControlUnitExtension(extensions.DeviceMixin, extensions.PluginExtension):
    """Omni plugin extension for Control Units """

    def __init__(self):
        self.type_ids = {"action": [],
                         "event": []}
        self.type_ids["device"] = [devtype for devtype, name
                                   in UnitProperties.device_types.values()]
        self.callbacks = {}

        extensions.DeviceMixin.__init__(self, UnitInfo, log)

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
            unit_info = self.info(dev.pluginProps["url"])
            method(action, dev, unit_num, unit_info)
            indigo.server.log('sent "{0}" {1} request'.format(dev.name, text))
        except (Py4JError, ConnectionError):
            log.error('send "{0}" {1} request failed'.format(dev.name, text))
            log.debug("", exc_info=True)

    def turn_on(self, action, dev, unit_num, unit_info):
        unit_info.send_command("CMD_UNIT_ON", 0, unit_num)

    def turn_off(self, action, dev, unit_num, unit_info):
        unit_info.send_command("CMD_UNIT_OFF", 0, unit_num)

    def toggle(self, action, dev, unit_num, unit_info):
        if dev.onState:
            self.turn_off(action, dev, unit_num, unit_info)
        else:
            self.turn_on(action, dev, unit_num, unit_info)

    def set_brightness(self, action, dev, unit_num, unit_info):
        unit_info.send_command("CMD_UNIT_PERCENT", action.actionValue,
                               unit_num)

    def brighten_by(self, action, dev, unit_num, unit_info):
        new_level = min(100, dev.brightness + action.actionValue)
        unit_info.send_command("CMD_UNIT_PERCENT", new_level, unit_num)

    def dim_by(self, action, dev, unit_num, unit_info):
        new_level = max(0, dev.brightness - action.actionValue)
        unit_info.send_command("CMD_UNIT_PERCENT", new_level, unit_num)

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


class UnitInfo(extensions.Info):
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
    reports = ["Control Units"]

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
        self.props = self.fetch_all_props(connection, UnitProperties,
                                          "UNIT", "NAMED", "AREA_ALL",
                                          "ANY_LOAD")
        log.debug("Units defined on Omni system: " +
                  ", ".join((zp.name for num, zp in self.props.items())))

    def fetch_status(self, objnum):
        """Given the number of a unit query the Omni controller for the
        current status of the unit and return a UnitStatus object.
        May raise ConnectionError or Py4JavaError if there is no valid
        connection or a network error.
        """
        if objnum not in self.props:
            raise ConnectionError("Unit {0} is not defined on Omni system")
        jomnilinkII = self.connection.jomnilinkII
        Message = jomnilinkII.Message
        status_msg = self.connection.omni.reqObjectStatus(
            Message.OBJ_TYPE_UNIT, objnum, objnum)
        status = status_msg.getStatuses()[0]
        return UnitStatus(self.props[objnum].has_brightness, status)

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
        if objnum not in self.props:
            log.debug("Ignoring status for unnamed unit {0}".format(objnum))
            return None, None

        log.debug("Received status for " + self.props[objnum].name)
        return objnum, UnitStatus(self.props[objnum].has_brightness,
                                  status)

    def report(self, report_name, say):
        items = sorted(self.props.items())
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

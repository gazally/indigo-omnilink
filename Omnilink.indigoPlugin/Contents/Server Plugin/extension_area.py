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

""" Omni Plugin extension for Areas """
from __future__ import unicode_literals
import logging

import indigo
from py4j.protocol import Py4JError

import extensions
from connection import ConnectionError

log = logging.getLogger(__name__)

_VERSION = "0.3.0"


class AreaExtension(extensions.DeviceMixin, extensions.PluginExtension):
    """Omni plugin extension for Areas """
    def __init__(self):
        self.type_ids = {"action": [],
                         "event": []}
        self.type_ids["device"] = ["omniAreaDevice"]
        self.callbacks = {}
        extensions.DeviceMixin.__init__(self, AreaInfo, log)


class AreaInfo(extensions.Info):
    """ Get the area info from the Omni device, and assist
    in fetching status, deciphering notification events and
    sending commands for areas.

    Public methods:
        number_and_status_from_notification: return name of area and AreaStatus
            object deciphered from Omni event notification method
        fetch_status: query Omni for area status for a area
        fetch_props: return a AreaProperties object for one area
        send_command: send a command
        report: given a print method, write formatted info about all areas
    """
    reports = ["Areas"]

    def __init__(self, connection):
        """ AreaInfo constructor
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
        self.controller_type = self._get_controller_type()
        self.props = self.fetch_all_props(connection, AreaProperties, "AREA",
                                          "NAMED_UNAMED", "NONE", "NONE")
        remove = [objnum for objnum, props in self.props.items()
                  if not props.enabled]
        for r in remove:
            del self.props[r]

        log.debug("Areas defined on Omni system: " +
                  ", ".join((str(ap.number)
                             for num, ap in self.props.items())))

    def _get_controller_type(self):
        return "Omni"

    def fetch_status(self, objnum):
        """Given the number of a area query the Omni controller for the
        current status of the area and return a AreaStatus object.
        May raise ConnectionError or Py4JavaError if there is no valid
        connection or a network error.
        """
        if objnum not in self.props:
            raise ConnectionError("Area {0} is not defined on Omni system")
        status_msg = self.connection.omni.reqObjectStatus(
            self.connection.jomnilinkII.Message.OBJ_TYPE_AREA, objnum, objnum)

        return AreaStatus(self.controller_type, status_msg.getStatuses()[0])

    def number_and_status_from_notification(self, status_msg):
        """ Given a status message from the JomniLinkII notification
        listener, determine if it is about a area. If it is, return the
        number of the area and a AreaStatus object, otherwise return
        (None, None)
        """
        Message = self.connection.jomnilinkII.Message
        if status_msg.getStatusType() != Message.OBJ_TYPE_AREA:
            return None, None

        status = status_msg.getStatuses()[0]
        objnum = status.getNumber()
        log.debug("Received status for " + self.props[objnum].name)

        return objnum, AreaStatus(self.controller_type, status)

    def send_command(self, cmd_name, area_num, parameter):
        """ Send the Omni controller a command, specified by name,
        along with the area number and parameter value.
        See comments in jomnilinkII.MessageTypes.CommandMessage
        for details.
        """
        cmd = getattr(self.connection.jomnilinkII.MessageTypes.CommandMessage,
                      cmd_name)
        self.connection.omni.controllerCommand(cmd, area_num, parameter)

    def report(self, report_name, say):
        items = sorted(self.props.items())
        if not items:
            say("None")
            return
        widths = [("Num", 4),
                  ("Name", 12),
                  ("Entry", 6),
                  ("Exit", 6),
                  ("Entry", 6),
                  ("Exit", 6),
                  ("Mode", 21)]

        fmt = "  ".join(("{{{0}: <{1}}}".format(i, w[1]) for i, w in
                         enumerate(widths)))
        say(fmt.format(*(n for n, w in widths)) +
            "Alarms")
        say(fmt.format("", "", "Delay", "Delay", "Timer", "Timer", ""))
        for num, ap in items:
            s = self.fetch_status(num)
            say(fmt.format(num, ap.name, ap.entry_delay, ap.exit_delay,
                           s.entry_timer, s.exit_timer, s.mode) +
                ", ".join(s.alarms))


class AreaProperties(extensions.Props):
    """ AreaProperties class, represents Omni  area properties """
    def __init__(self, omni_props):
        """ Construct a AreaProperties object from the jomnilinkII
        Area Properties object.
        """
        self.number = omni_props.getNumber()
        self.name = omni_props.getName()
        if not self.name:
            self.name = "Area {0}".format(self.number)
        self.enabled = omni_props.isEnabled()
        self.exit_delay = omni_props.getExitDelay()
        self.entry_delay = omni_props.getEntryDelay()
        self.device_type = "omniAreaDevice"
        self.type_name = "Area"

    def device_states(self):
        return {"name": self.name,
                "exitDelay": self.exit_delay,
                "entryDelay": self.entry_delay}


class AreaStatus(extensions.Status):
    """ AreaStatus class, represents Omni Area status """
    def __init__(self, controller_type, omni_status):
        """ Construct a AreaStatus object from a jomnilinkII
        Area Status object. """
        mode = omni_status.getMode()

        self.mode = self.mode_names[controller_type].get(
            mode & self.mode_delay_mask, "Unknown")
        if mode & self.mode_delay_bit:
            change_delay = "Arming" if controller_type == "Omni" else "Setting"
            self.mode = change_delay + " " + self.mode

        alarms = omni_status.getAlarms()
        self.alarms = []
        for i, alarm in enumerate(self.alarm_names):
            if alarms & 1 << i:
                self.alarms.append(alarm)

        self.entry_timer = omni_status.getEntryTimer()
        self.exit_timer = omni_status.getExitTimer()

    def device_states(self):
        results = {"mode": self.mode,
                   "entryTimer": self.entry_timer,
                   "exitTimer": self.exit_timer}
        for alarm in self.alarm_names:
            results["alarm" + alarm] = alarm in self.alarms
        return results

    mode_names = {"Omni": {0: "Off", 1: "Day", 2: "Night",
                           3: "Away", 4: "Vacation", 5: "Day Instant",
                           6: "Night Delayed"},
                  "Lumina": {1: "Home", 2: "Sleep", 3: "Away",
                             4: "Vacation", 5: "Party", 6: "Special"}
                  }
    mode_delay_bit = 0b1000
    mode_delay_mask = 0b0111

    alarm_names = ["Burglary", "Fire", "Gas", "Auxiliary", "Freeze", "Water",
                   "Duress", "Temperature"]

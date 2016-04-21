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
import connection
from connection import ConnectionError

log = logging.getLogger(__name__)

_VERSION = "0.3.0"


class AreaExtension(extensions.PluginExtension):
    """Omni plugin extension for Areas """
    def __init__(self):
        self.type_ids = {"action": [],
                         "event": []}
        self.type_ids["device"] = ["omniAreaDevice"]
        self.callbacks = {}
        self.reports = {"Areas": self.say_area_info}

        self.device_ids = []

        # key is url, list is AreaInfo instances
        self._area_info = {}

    # ----- Device Start and Stop Methods ----- #

    def deviceStartComm(self, device):
        """Start one of the area devices. Query the Omni system and
        set the status of the indigo device.
        """
        log.debug('Starting device "{0}"'.format(device.name))
        if device.id not in self.device_ids:
            self.device_ids.append(device.id)

        self.update_device_status(device)

    def deviceStopComm(self, device):
        if device.id in self.device_ids:
            log.debug('Stopping device "{0}"'.format(device.name))
            self.device_ids.remove(device.id)

    # ----- Device creation methods ----- #

    def getDeviceList(self, url, dev_ids):
        """ Query the Omni controller to see if any areas are defined.
        If there are, return the area device type.
        Otherwise, return an empty list.
        """
        result = []
        try:
            if self.area_info(url).area_props:
                result = [("omniAreaDevice", "Area")]
        except (Py4JError, ConnectionError):
            log.error("Failed to fetch area information from the "
                      "Omni Controller")
            log.debug("", exc_info=True)
        return result

    def createDevices(self, dev_type, values, prefix, dev_ids):
        """Automatically create a device for each area, unless it
        already exists.
        """
        old_devs = [
            indigo.devices[id] for id in dev_ids
            if indigo.devices[id].deviceTypeId == dev_type]
        values["deviceVersion"] = _VERSION
        try:
            for ap in self.area_info(values["url"]).area_props.values():
                if not any((dev.pluginProps["number"] == ap.number
                            for dev in old_devs)):
                    self.create_device(ap, values, prefix)
        except (Py4JError, ConnectionError):
            log.error("Failed to fetch area information from the "
                      "Omni Controller")
            log.debug("", exc_info=True)

    def create_device(self, area_props, values, prefix):
        """Create a new device, given area properties and device
        properties.
        """
        log.debug("Creating area device for {0}:{1}".format(area_props.number,
                                                            area_props.name))
        values["number"] = area_props.number
        kwargs = {"props": values,
                  "deviceTypeId": "omniAreaDevice"}
        name = self.get_unique_name(prefix, area_props.name)
        if name:
            kwargs["name"] = name
        newdev = indigo.device.create(indigo.kProtocol.Plugin, **kwargs)
        newdev.model = self.MODEL
        newdev.subModel = "Area"
        newdev.replaceOnServer()

    # ----- Callbacks from OMNI Status and events ----- #

    def status_notification(self, connection, status_msg):
        try:
            if (status_msg.getStatusType() !=
                    connection.jomnilinkII.Message.OBJ_TYPE_AREA):
                return
            area_info = self.area_info(connection.url)
            number, status = area_info.number_and_status_from_notification(
                status_msg)
        except (Py4JError, ConnectionError):
            log.debug("status_notification exception in Area", exc_info=True)
        else:
            for dev in self.devices_from_url(connection.url):
                if dev.pluginProps["number"] == number:
                    self.update_device_from_status(dev, status)

    def reconnect_notification(self, connection, omni):
        for dev in self.devices_from_url(connection.url):
            self.update_device_status(dev)

    def disconnect_notification(self, connection, e):
        for dev in self.devices_from_url(connection.url):
            dev.setErrorStateOnServer("disconnected")

    def devices_from_url(self, url):
        """ Produce an iteration of device objects matching the given url
        by selecting from self.device_ids """
        for dev_id in self.device_ids:
            dev = indigo.devices[dev_id]
            if (url == dev.pluginProps["url"]):
                yield dev

    def update_device_status(self, dev):
        area_num = dev.pluginProps["number"]
        try:
            area_info = self.area_info(dev.pluginProps["url"])
            props = area_info.area_props[area_num]
            status = area_info.fetch_status(area_num)
        except (ConnectionError, Py4JError):
            log.debug("Failed to get status of area {0} from Omni".format(
                area_num))
            dev.setErrorStateOnServer("disconnected")
            return

        for k, v in props.device_states().items():
            dev.updateStateOnServer(k, v)
        self.update_device_from_status(dev, status)
        dev.setErrorStateOnServer(None)

    def update_device_from_status(self, dev, status):
        for k, v in status.device_states().items():
            dev.updateStateOnServer(k, v)

    def area_info(self, url):
        """ Handles caching AreaInfo objects by url. Makes a new one if
        we don't have it yet for that url or if the underlying connection
        object has changed. """
        connection = self.plugin.make_connection(url)
        if (url not in self._area_info or
                self._area_info[url].connection is not connection):
            self._area_info[url] = AreaInfo(connection)

        return self._area_info[url]

    # ----- Write info on areas to log ----- #

    def say_area_info(self, report, connection, say):
        area_info = self.area_info(connection.url)
        area_info.report(say)


class AreaInfo(object):
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
        self.area_props = self._fetch_all_props()
        log.debug("Areas defined on Omni system: " +
                  ", ".join((str(ap.number)
                             for num, ap in self.area_props.items())))

    def _get_controller_type(self):
        return "Omni"

    def _fetch_all_props(self):
        """ Query the connected Omni device for the properties of all the
        named areas. Build AreaProperties objects out of them, ignoring the
        statuses, and return a dictionary indexed by object number.
        Raises Py4JJavaError or ConnectionError if there is a
        network error """
        Message = self.connection.jomnilinkII.Message
        ObjectProps = self.connection.jomnilinkII.MessageTypes.ObjectProperties
        objnum = 0
        results = {}
        while True:
            m = self.connection.omni.reqObjectProperties(
                Message.OBJ_TYPE_AREA,
                objnum, 1,
                ObjectProps.FILTER_1_NAMED_UNAMED,
                ObjectProps.FILTER_2_NONE,
                ObjectProps.FILTER_3_NONE)
            if m.getMessageType() != Message.MESG_TYPE_OBJ_PROP:
                break
            objnum = m.getNumber()
            props = AreaProperties(m)
            if props.enabled:
                results[objnum] = props
        return results

    def fetch_status(self, objnum):
        """Given the number of a area query the Omni controller for the
        current status of the area and return a AreaStatus object.
        May raise ConnectionError or Py4JavaError if there is no valid
        connection or a network error.
        """
        if objnum not in self.area_props:
            raise ConnectionError("Area {0} is not defined on Omni system")
        jomnilinkII = self.connection.jomnilinkII
        Message = jomnilinkII.Message
        status_msg = self.connection.omni.reqObjectStatus(
            Message.OBJ_TYPE_AREA, objnum, objnum)
        status = status_msg.getStatuses()[0]
        return AreaStatus(self.controller_type, status)

    def number_and_status_from_notification(self, status_msg):
        """ Given a status message from the JomniLinkII notification
        listener, determine if it is about a area. If it is, return the
        number of the area and a AreaStatus object, otherwise return
        (None, None)
        """
        Message = self.connection.jomnilinkII.Message
        if status_msg.getStatusType() != Message.OBJ_TYPE_AREA:
            return None, None

        statuses = status_msg.getStatuses()
        status = statuses[0]
        objnum = status.getNumber()
        log.debug("Received status for " + self.area_props[objnum].name)

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

    def report(self, say):
        items = sorted(self.area_props.items())
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


class AreaProperties(object):
    """ AreaProperties class, represents Omni control area properties """
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

    def device_states(self):
        return {"name" : self.name,
                "exitDelay" : self.exit_delay,
                "entryDelay" : self.entry_delay}


class AreaStatus(object):
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

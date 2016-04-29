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
from collections import defaultdict
import datetime
from distutils.version import StrictVersion
import logging

import indigo
from py4j.protocol import Py4JError

import extensions
from connection import ConnectionError
from properties import AreaProperties, AreaStatus, ControllerProps

log = logging.getLogger(__name__)

_VERSION = "0.4.0"


class AreaExtension(extensions.DeviceMixin, extensions.PluginExtension):
    """Omni plugin extension for Areas """
    def __init__(self):
        self.type_ids = {"action": ["checkSecurityCode",
                                    "armSecuritySystem",
                                    "armSecuritySystemAll",
                                    "bypassZone",
                                    "restoreZone",
                                    "restoreAllZones",
                                    "restoreAllZonesAllAreas"],
                         "event": []}

        self.type_ids["device"] = ["omniAreaDevice"]

        self.callbacks = {"checkSecurityCode": self.checkSecurityCode,
                          "generateModeList": self.generateModeList,
                          "armSecuritySystem": self.armSecuritySystem,
                          "bypassRestoreZone": self.bypassRestoreZone}

        self.last_clock_tick = datetime.datetime.now()

        # key is device id, value is dictionary mapping device state names
        # to tuples (initial timer value in seconds, timestamp)
        self.timestamps = defaultdict(dict)

        extensions.DeviceMixin.__init__(self, AreaInfo, log)

    # ----- Update device states ----- #

    def update(self):
        """ Called from the plugin's runConcurrentThread loop.
        Every half a second, update any countdown timers in the
        device states, until they reach zero.
        """
        if (datetime.datetime.now() - self.last_clock_tick <
                datetime.timedelta(seconds=0.5)):
            return
        self.last_clock_tick = datetime.datetime.now()
        for device_id_list in self.device_ids.values():
            for dev_id in device_id_list:
                dev = indigo.devices[dev_id]

                self.update_timer_state(dev, "entryTimer")
                self.update_timer_state(dev, "exitTimer")

    def update_timer_state(self, dev, statename):
        """ Update a timer state for a device. """
        if not dev.states[statename]:
            return
        seconds, last_status = self.timestamps[dev.id][statename]
        delta = (datetime.datetime.now() - last_status).seconds
        dev.updateStateOnServer(statename, max(0, seconds - delta))

    # ----- Maintenance of device states ----- #

    def update_device_status(self, dev):
        """ Update device status, and reset the last checked code states """
        self.update_last_checked_code(dev)
        extensions.DeviceMixin.update_device_status(self, dev)

    def update_device_from_status(self, dev, status):
        """ In addition to updating the device from a status, save the
        current time so that timer countdowns can be done, and test if any
        of the alarm states have changed """
        self.set_timer_timestamps(dev, status)
        extensions.DeviceMixin.update_device_from_status(self, dev, status)

    def set_timer_timestamps(self, dev, status):
        newstates = status.device_states()
        for s in ["entryTimer", "exitTimer"]:
            if newstates[s]:
                self.timestamps[dev.id][s] = (newstates[s],
                                              datetime.datetime.now())
    authority = {0: "Invalid",
                 1: "Master",
                 2: "Manager",
                 3: "User",
                 "N/A": "N/A",
                 "Error": "Error"}

    def update_last_checked_code(self, device, code="None",
                                 authority="N/A", user="N/A"):
        """ Set device states for the last checked security code.
        Defaults are for initialization when no code has been
        checked yet.
        """
        device.updateStateOnServer("lastCheckedCodeAuthority",
                                   self.authority.get(authority,
                                                      "Unknown"))
        device.updateStateOnServer("lastCheckedCodeUser", user)
        device.updateStateOnServer("lastCheckedCodeDuress", user == 251)
        device.updateStateOnServer("lastCheckedCode", code)

    # ----- Action Config UI ----- #

    def getActionConfigUiValues(self, values, type_id, device_id):
        """ called by the Indigo UI before the Action configuration dialog
        is shown to the user.
        """
        log.debug("getActionConfigUiValues called for {0}".format(type_id))
        errors = indigo.Dict()

        if type_id == "armSecuritySystem" or type_id == "armSecuritySystemAll":
            if not values.get("mode", ""):
                values["mode"] = "1"

        if type_id != "checkSecurityCode":
            with extensions.comm_error_logging(log):
                info = self.info(indigo.devices[device_id].pluginProps["url"])
                values["user_max"] = info.maximum_user_number

        return (values, errors)

    def generateModeList(self, filter, values, type_id, device_id):
        """ Generate list of arm/disarm or lighting modes for the
        arm/disarm action configuration ui.
        """
        log.debug("generateModeList called, {0}, {1}, {2}, {3}".format(
            filter, values, type_id, device_id))
        device = indigo.devices[device_id]
        results = {}

        with extensions.comm_error_logging(log):
            info = self.info(device.pluginProps["url"])
            modes = AreaStatus.mode_names[info.controller_type].items()
            for k, v in modes:
                if k == 0:
                    results[str(k)] = "Disarm"
                else:
                    results[str(k)] = v + " Mode"

        return sorted(results.items())

    def validateActionConfigUi(self, values, type_id, action_id):
        """ called by the Indigo UI to validate the values dictionary
        for the Action user interface dialog
        """
        log.debug("Action Validation called for %s" % type_id)
        errors = indigo.Dict()
        if (StrictVersion(values.get("actionVersion", "0.0")) <
                StrictVersion(_VERSION)):
            values["actionVersion"] = _VERSION

        if type_id == "checkSecurityCode":
            code = values["code"]
            if "%%" in code:
                self.validate_substitution(values, errors, "code")
            elif not self.is_valid_code(code):
                errors["code"] = ("Security codes must be four digits: "
                                  "0001 to 9999")
        else:
            user = values["user"]
            if "%%" in user:
                self.validate_substitution(values, errors, "user")
            else:
                try:
                    self.user_number(values, values["user_max"])
                except ValueError:
                    errors["user"] = ("Please enter the user number to arm or "
                                      "disarm with, not the user code")
        return (not errors, values, errors)

    def validate_substitution(self, values, errors, field):
        tup = self.plugin.substitute(values[field], validateOnly=True)
        valid = tup[0]
        if not valid:
            errors[field] = tup[1]

    def user_number(self, values, user_max, do_substitute=False):
        user = values.get("user", "")
        if do_substitute:
            user = self.plugin.substitute(user, validateOnly=False)
        if len(user) == 4:
            raise ValueError
        num = int(user)
        if num < 1 or num > user_max:
            raise ValueError
        return num

    def is_valid_code(self, code):
        return (len(code) == 4 and
                code != "0000" and
                all(['0' <= ch <= '9' for ch in code]))

    # ----- Action callbacks ----- #

    def armSecuritySystem(self, action):
        """ Callback for the arm/disarm security system action """
        if (action.deviceId not in indigo.devices or
                "user" not in action.props):
            log.error("{0} action not configured".format(action.pluginTypeId))
            return

        dev = indigo.devices[action.deviceId]
        info = self.info(dev.pluginProps["url"])
        try:
            user = self.user_number(action.props, info.maximum_user_number,
                                    True)
        except ValueError:
            log.error("armSecuritySystem given invalid user number "
                      '"{0}"'.format(action.props.get("user", "")))
            return

        mode = action.props.get("mode", "")
        try:
            mode = int(mode)
            AreaStatus.mode_names[info.controller_type][mode]
        except (KeyError, ValueError):
            log.error("armSecuritySystem given invalid mode {0}".format(
                mode))
            return

        if dev.deviceTypeId == "omniAreaDevice":
            area = dev.pluginProps["number"]
        else:
            area = 0

        log.debug("armSecuritySystem called with user {0}, area {1}, "
                  "mode {2}".format(user, area, mode))

        with extensions.comm_error_logging(log):
            area_info = self.info(dev.pluginProps["url"])
            area_info.send_mode_command(mode, user, area)

    def checkSecurityCode(self, action):
        """ Callback for Validate Security Code action
        """
        if (action.deviceId not in indigo.devices or
                "code" not in action.props):
            log.error("{0} action not configured".format(action.pluginTypeId))
            return

        dev = indigo.devices[action.deviceId]
        if dev.deviceTypeId != "omniAreaDevice":
            log.error("Old version of Check Security Code action. "
                      "Please delete and re-create it. ")
            return

        code = self.plugin.substitute(action.props.get("code", ""))
        area = dev.pluginProps["number"]

        log.debug("checkSecurity code called for code {0} in area {1}".format(
            code, area))

        if not self.is_valid_code(code):
            log.error("checkSecurityCode asked to validate "
                      "'{0}' which is not between 0001 and 9999".format(code))
        else:
            with extensions.comm_error_logging(log):
                c = self.plugin.make_connection(dev.pluginProps["url"])
                scv = c.omni.reqSecurityCodeValidation(
                    int(area), *[ord(ch) - ord("0") for ch in code])

                self.update_last_checked_code(
                    dev, code=code, authority=scv.getAuthorityLevel(),
                    user=scv.getCodeNumber())
                log.debug("code {0} has authority {1} in area {2} "
                          "user number {3}".format(
                              code, scv.getAuthorityLevel(), area,
                              scv.getCodeNumber()))
                return

        self.update_last_checked_code(dev, code=code, authority="Error")

    def bypassRestoreZone(self, action):
        """ Callback for the bypassing and restoring zones action """
        if (action.deviceId not in indigo.devices or
                "user" not in action.props):
            log.error("{0} action not configured".format(action.pluginTypeId))
            return

        dev = indigo.devices[action.deviceId]
        number = dev.pluginProps["number"]

        try:
            info = self.info(dev.pluginProps["url"])
            user = self.user_number(action.props, info.maximum_user_number,
                                    True)
        except ValueError:
            log.error("Bypass/Restore zone action given invalid user "
                      'number "{0}"'.format(action.props.get("user", "")))
            return
        except (Py4JError, ConnectionError):
            log.error("Error communicating with Omni controller")
            log.debug("", exc_info=True)
            return

        if action.pluginTypeId == "bypassZone":
            cmd_name = "CMD_SECURITY_BYPASS_ZONE"
        else:
            if dev.deviceTypeId == "omniZoneDevice":
                cmd_name = "CMD_SECURITY_RESTORE_ZONE"
            else:
                cmd_name = "CMD_SECURITY_RESTORE_ALL_ZONES"
                if dev.deviceTypeId == "omniControllerDevice":
                    number = 0  # All zones in all areas

        log.debug("{0} called, user code {1}, area/zone number {2}".format(
            action.pluginTypeId, user, number))

        try:
            info.send_command(cmd_name, user, number)
        except (Py4JError, ConnectionError):
            log.error("Bypass/Restore command failed")
            log.debug("", exc_info=True)
            return


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
        self.maximum_user_number = self._get_maximum_user_number()
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
        props = ControllerProps(self.connection)
        return props.base_model

    def _get_maximum_user_number(self):
        M = self.connection.jomnilinkII.Message
        return self.connection.omni.reqObjectTypeCapacities(
            M.OBJ_TYPE_CODE).getCapacity()

    def fetch_status(self, objnum):
        """Given the number of a area query the Omni controller for the
        current status of the area and return a AreaStatus object.
        May raise ConnectionError or Py4JavaError if there is no valid
        connection or a network error.
        """
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
        if objnum not in self.props:
            log.debug("Ignoring status for disabled area {0}".format(objnum))
            return None, None

        log.debug("Received status for " + self.props[objnum].name)

        return objnum, AreaStatus(self.controller_type, status)

    def send_mode_command(self, mode, user, area):
        """ Send the Omni controller an arm/disarm command """
        CM = self.connection.jomnilinkII.MessageTypes.CommandMessage
        self.connection.omni.controllerCommand(
            CM.CMD_SECURITY_OMNI_DISARM + mode, user, area)

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

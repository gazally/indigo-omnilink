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

""" Omni Plugin extension for Controller Devices """
from __future__ import unicode_literals
from collections import namedtuple, defaultdict
from datetime import time, datetime
from distutils.version import StrictVersion
import logging

import indigo
from py4j.protocol import Py4JError

from connection import ConnectionError
import extensions

log = logging.getLogger(__name__)

_VERSION = "0.3.0"

# to do -- update the battery reading periodically (like once a day)
# action - set time in controller automatically
# to do - UIDisplayStateId should be based on troubles not connection
# action - acknowledge troubles


class ControllerExtension(extensions.PluginExtension):
    """Omni plugin extension for Controller devices """
    def __init__(self):
        self.type_ids = {"device": ["omniControllerDevice"],
                         "action": ["checkSecurityCode",
                                    "enableConsoleBeeper",
                                    "disableConsoleBeeper",
                                    "sendBeepCommand"],
                         "event": ["phoneLineDead", "phoneLineRing",
                                   "phoneLineOffHook", "phoneLineOnHook",
                                   "ACPowerOff", "ACPowerOn",
                                   "batteryLow", "batteryOK",
                                   "digitalCommunicatorModuleTrouble",
                                   "digitalCommunicatorModuleOK",
                                   "energyCostLow", "energyCostMid",
                                   "energyCostHigh", "energyCostCritical"]}
        self.device_ids = []

        # for each device contains a dict
        # which maps event type -> list of triggers
        self.triggers = {}

        self.callbacks = {
            "checkSecurityCode": self.checkSecurityCode,
            "generateConsoleList": self.generateConsoleList,
            "enableConsoleBeeper": self.enableDisableConsoleBeeper,
            "disableConsoleBeeper": self.enableDisableConsoleBeeper,
            "sendBeepCommand": self.sendBeepCommand
        }

        self.reports = {"System Information": self.say_system_information,
                        "System Troubles": self.say_system_troubles,
                        "System Capacities": self.say_system_capacities,
                        "Event Log": self.say_event_log}

        self.controller_info = {}

    # ----- Device Start and Stop Methods ----- #

    def deviceStartComm(self, device):
        """ start an omniControllerDevice. Query the Omni system and set
        the states of the indigo device. """
        log.debug('Starting device "{0}"'.format(device.name))
        if device not in self.device_ids:
            self.device_ids.append(device.id)
            self.triggers[device.id] = defaultdict(list)
            self.update_device_version(device)
            self.update_device_status(device)

    def deviceStopComm(self, device):
        if device.id in self.device_ids:
            log.debug('Stopping device "{0}"'.format(device.name))
            self.device_ids.remove(device.id)
            del self.triggers[device.id]

    # ----- Maintenance of device states ----- #

    def update_device_version(self, device):
        """ if the device was defined in a previous version of this plugin,
        update it and change the version number. Note that
        replacePluginPropsOnServer calls deviceStartComm, so it's important
        to avoid calling it if nothing needs to be changed.
        """
        device_version = device.pluginProps.get("deviceVersion", "0.0")
        if (StrictVersion(device_version) >= StrictVersion(_VERSION)):
            return

        log.debug("Updating device {0} from version {1} "
                  "to version {2}".format(device.id, device_version,
                                          _VERSION))
        device.stateListOrDisplayStateIdChanged()

        # device.pluginProps always creates a copy of itself
        props = device.pluginProps
        props["deviceVersion"] = _VERSION
        device.replacePluginPropsOnServer(props)

    def update_device_status(self, device):
        """ Ask the controller for information and set the
        device states accordingly, and clear the last checked
        security code.
        """
        connection = self.plugin.make_connection(device.pluginProps["url"])
        try:
            info = self.get_controller_info(connection)
            device.updateStateOnServer("connected", True)
            device.updateStateOnServer("model", info.model)
            device.updateStateOnServer("firmwareVersion", info.firmware)
            device.updateStateOnServer("batteryReading", info.battery_reading)

            self.update_last_checked_code(device)

            for t, value in info.troubles.items():
                device.updateStateOnServer(t, value)
            device.setErrorStateOnServer(None)

        except (Py4JError, ConnectionError):
            log.error("Could not get status of Omni Controller")
            log.debug("", exc_info=True)
            device.updateStateOnServer("connected", False)
            device.setErrorStateOnServer("not connected")

    authority = {0: "Invalid",
                 1: "Master",
                 2: "Manager",
                 3: "User",
                 "N/A": "N/A",
                 "Error": "Error"}

    def update_last_checked_code(self, device,
                                 code="None", area="None",
                                 authority="N/A", user="N/A"):
        """ Set device states for the last checked security code.
        Defaults are for initialization when no code has been
        checked yet.
        """
        device.updateStateOnServer("lastCheckedCodeArea", area)
        device.updateStateOnServer("lastCheckedCodeAuthority",
                                   self.authority.get(authority,
                                                      "Unknown"))
        device.updateStateOnServer("lastCheckedCodeUser", user)
        device.updateStateOnServer("lastCheckedCodeDuress", user == 251)
        device.updateStateOnServer("lastCheckedCode", code)

    models = {30: "HAI Omni IIe",
              16: "HAI OmniPro II",
              36: "HAI Lumina",
              37: "HAI Lumina Pro",
              38: "HAI Omni LTe"}

    trouble_names = ["freezeTrouble", "batteryLowTrouble", "ACPowerTrouble",
                     "phoneLineTrouble", "digitalCommunicatorTrouble",
                     "fuseTrouble", "freezeTrouble", "batteryLowTrouble"]

    def get_controller_info(self, connection):
        """ Query an Omni controller for its status and put the results into a
        namedtuple. See SystemInformation.java, SystemStatus.java
        and SystemTroubles.java for explanations of the data coming from
        jomnilinkII.
        """
        info = connection.omni.reqSystemInformation()
        model, firmware = self.decode_system_info(info)

        status = connection.omni.reqSystemStatus()
        battery_reading = status.getBatteryReading()

        troubles = connection.omni.reqSystemTroubles()
        trouble_states = self.decode_troubles(troubles)

        return namedtuple(
            "Info", ["model", "firmware", "battery_reading", "troubles"])(
                model, firmware, battery_reading, trouble_states)

    def decode_system_info(self, info):
        model = self.models.get(info.getModel(), "Unknown")
        major = info.getMajor()
        minor = info.getMinor()
        revision_number = info.getRevision()
        if revision_number == 0:
            # no revision number
            revision = ""
        elif revision_number < 26:
            # revisions a through z
            revision = chr(ord('a') + revision_number - 1)
        else:
            # prototype revisions X1, X2 etc.
            revision = "X" + str(256 - revision_number)
        firmware = "{0}.{1}{2}".format(major, minor, revision)
        return model, firmware

    def decode_troubles(self, troubles):
        trouble_states = {}
        for t in self.trouble_names:
            trouble_states[t] = False
        for t in troubles.getTroubles():
            trouble_states[self.trouble_names[t - 1]] = True
        return trouble_states

    # ----- Device creation ----- #

    def getDeviceList(self, url, dev_ids):
        """ Return list of devices this extension can create """
        return [("omniControllerDevice", "Controller")]

    def createDevices(self, dev_type, props, prefix, dev_ids):
        """ Automatically create a controller device, unless there is one
        already.
        """
        for dev_id in dev_ids:
            if indigo.devices[dev_id].deviceTypeId == dev_type:
                return
        log.debug("Creating controller device")

        props["deviceVersion"] = _VERSION
        kwargs = {"props": props,
                  "deviceTypeId": dev_type}
        name = self.get_unique_name(prefix, "Controller")
        if name:
            kwargs["name"] = name

        newdev = indigo.device.create(indigo.kProtocol.Plugin, **kwargs)
        newdev.model = self.MODEL
        newdev.subModel = "Controller"
        newdev.replaceOnServer()

    def update(self):
        # periodically inquire about battery reading
        pass

    # ----- Callbacks from OMNI Status and events ----- #

    notification_mask = 0xFF00
    event_mask = 0x00FF
    notification_value = 0x0300
    event_types = {0: "phoneLineDead",
                   1: "phoneLineRing",
                   2: "phoneLineOffHook",
                   3: "phoneLineOnHook",

                   4: "ACPowerOff",
                   5: "ACPowerRestored",

                   6: "batteryLow",
                   7: "batteryOK",

                   8: "digitalCommunicatorModuleTrouble",
                   9: "digitalCommunicatorModuleOK",

                   10: "energyCostLow",
                   11: "energyCostMid",
                   12: "energyCostHigh",
                   13: "energyCostCritical"}

    def event_notification(self, connection, other_event_msg):
        """ Callback used by plugin when it receives an Other Event
        Notification from the Omni controller. Decode the events
        that are pertinent to the controller functionality, and set
        off any active triggers.
        """
        try:
            dev = self.find_device_from_connection(connection)
            triggers = self.triggers[dev.id]
        except KeyError:
            return
        log.debug('Received "other event" notification for device {0}'.format(
            dev.id))
        try:
            notifications = other_event_msg.getNotifications()
            for n in notifications:
                log.debug("Notification code: " + hex(n))
                if n & self.notification_mask == self.notification_value:
                    event_num = n & self.event_mask
                    if event_num in self.event_types:
                        event_type = self.event_types[event_num]
                        log.debug("Processing {0} event for device {1}".format(
                            event_type, dev.id))
                        for t in self.triggers[dev.id][event_type]:
                            indigo.trigger.execute(t)
        except Py4JError:
            log.error("Unable to decode event notification", exc_info=True)

        self.update_device_status(dev)

    def reconnect_notification(self, connection, omni):
        """ Callback used by plugin when successful reconnection
        is made to the Omni controller. Refresh device states.
        """
        try:
            dev = self.find_device_from_connection(connection)
            self.update_device_status(dev)
        except KeyError:
            return

    def disconnect_notification(self, connection, e):
        """ Callback used by plugin when a disconnect message is
        received from the jomnilinkII library. Put all devices into
        the error state. """
        try:
            dev = self.find_device_from_connection(connection)
            dev.updateStateOnServer("connected", False)
            dev.setErrorStateOnServer("not connected")
        except KeyError:
            return

    def find_device_from_connection(self, connection):
        """ Given a connection, try to find a device with
        matching url. If not found, raise a KeyError.
        """
        url = connection.url
        for dev_id in self.device_ids:
            dev = indigo.devices[dev_id]
            if (dev.pluginProps["url"] == url):
                return dev
        raise KeyError

    # ----- Trigger Start and Stop Methods ----- #

    def triggerStartProcessing(self, trigger):
        log.debug(
            "Start processing {0} trigger {1}".format(trigger.pluginTypeId,
                                                      str(trigger.id)))
        try:
            dev_id = int(trigger.pluginProps["controllerId"])
            triggers = self.triggers[dev_id][trigger.pluginTypeId]
            if trigger.id not in triggers:
                triggers.append(trigger.id)
        except KeyError:
            log.error("Trigger {0} is configured incorrectly".format(
                trigger.id))
            log.debug("", exc_info=True)

    def triggerStopProcessing(self, trigger):
        log.debug(
            "Stop processing {0} trigger {1}".format(trigger.pluginTypeId,
                                                     trigger.id))
        try:
            dev_id = int(trigger.pluginProps["controllerId"])
            triggers = self.triggers[dev_id][trigger.pluginTypeId]
            triggers.remove(trigger.id)
        except (KeyError, ValueError):
            pass  # deviceStopComm already removed it from the list

    # ----- Action Item Config UI ----- #

    def getActionConfigUiValues(self, values, type_id, device_id):
        """ called by the Indigo UI before the Action configuration dialog
        is shown to the user.
        """
        log.debug("getActionConfigUiValues called")
        errors = indigo.Dict()

        if type_id == "sendBeepCommand" and not values.get("beepCommand", ""):
            values["beepCommand"] = "beepOff"

        if type_id in ["sendBeepCommand", "enableConsoleBeeper",
                       "disableConsoleBeeper"]:
            if not values.get("consoleNumber", ""):
                values["consoleNumber"] = "0"

        return (values, errors)

    def generateConsoleList(self, filter, values, type_id, device_id):
        log.debug("generateConsoleList called, {0}, {1}, {2}, {3}".format(
            filter, values, type_id, device_id))
        results = [("0", "All Keypads")]
        device = indigo.devices[device_id]
        try:
            c = self.plugin.make_connection(device.pluginProps["url"])
            M = c.jomnilinkII.Message
            count = c.omni.reqObjectTypeCapacities(
                M.OBJ_TYPE_CONSOLE).getCapacity()
            results = results + [(str(i), "Keypad {0}".format(i))
                                 for i in range(1, count + 1)]
        except (Py4JError, ConnectionError):
            log.error("Failed to get keypad count from Omni controller")
            log.debug("", exc_info=True)

        return results

    def validateActionConfigUi(self, values, type_id, action_id):
        """ called by the Indigo UI to validate the values dictionary
        for the Action user interface dialog
        """
        log.debug("Action Validation called for %s" % type_id)
        errors = indigo.Dict()
        if (StrictVersion(values.get("actionVersion", "0.0")) <
                StrictVersion(_VERSION)):
            values["actionVersion"] = _VERSION

        if type_id != "checkSecurityCode":
            return (not errors, values, errors)

        code = values["code"]
        if "%%" in code:
            self.validate_substitution(values, errors, "code")
        elif not self.is_valid_code(code):
            errors["code"] = "Security codes must be four digits: 0001 to 9999"

        area = values["area"]
        if "%%" in area:
            self.validate_substitution(values, errors, "area")
        elif not self.is_valid_area(area):
            errors["area"] = ("Please enter the area number in which to check "
                              "the security code")

        return (not errors, values, errors)

    def validate_substitution(self, values, errors, field):
        tup = self.plugin.substitute(values[field], validateOnly=True)
        valid = tup[0]
        if not valid:
            errors[field] = tup[1]

    def is_valid_code(self, code):
        return (len(code) == 4 and
                code != "0000" and
                all(['0' <= ch <= '9' for ch in code]))

    def is_valid_area(self, area):
        try:
            if int(area) < 1 or int(area) > 255:
                return False
        except ValueError:
            return False
        return True

    # ----- Action Item Callbacks ----- #

    def checkSecurityCode(self, action):
        """ Callback for Validate Security Code action
        """
        dev = indigo.devices[action.deviceId]
        code = self.plugin.substitute(action.props.get("code", ""))
        area = self.plugin.substitute(action.props.get("area", ""))
        log.debug("checkSecurity code called for code {0} in area {1}".format(
            code, area))

        if not self.is_valid_code(code):
            log.error("checkSecurityCode asked to validate "
                      "'{0}' which is not between 0001 and 9999".format(code))
        elif not self.is_valid_area(area):
            log.error("checkSecurityCode asked to validate code in area "
                      "{0} which is not between 1 and 255".format(area))
        else:
            try:
                c = self.plugin.make_connection(dev.pluginProps["url"])
                scv = c.omni.reqSecurityCodeValidation(
                    int(area), *[ord(ch) - ord("0") for ch in code])

                self.update_last_checked_code(
                    dev, code=code, area=area,
                    authority=scv.getAuthorityLevel(),
                    user=scv.getCodeNumber())
                log.debug("code {0} has authority {1} in area {2} "
                          "user number {3}".format(
                              code, scv.getAuthorityLevel(), area,
                              scv.getCodeNumber()))
                return

            except (Py4JError, ConnectionError):
                log.error("Error communicating with Omni Controller")
                log.debug("", exc_info=True)

        self.update_last_checked_code(dev, code=code, area=area,
                                      authority="Error")

    def enableDisableConsoleBeeper(self, action):
        """ Callback for enableConsoleBeeper and disableConsoleBeeper. """
        dev = indigo.devices[action.deviceId]
        if not action.props.get("consoleNumber", False):
            log.error("{0} not configured".format(action.pluginTypeId))
            return
        log.debug('{0} called for device "{1}" console {2}'.format(
            action.pluginTypeId, dev.name, action.props["consoleNumber"]))

        enable = 1 if action.pluginTypeId == "enableConsoleBeeper" else 0
        try:
            c = self.plugin.make_connection(dev.pluginProps["url"])
            CM = c.jomnilinkII.MessageTypes.CommandMessage
            console = int(action.props["consoleNumber"])
            c.omni.controllerCommand(CM.CMD_CONSOLE_ENABLE_DISABLE_BEEPER,
                                     enable, console)
        except (Py4JError, ConnectionError):
            log.error("Error sending beep enable/disable to Omni Controller")
            log.debug("", exc_info=True)
        except ValueError:
            log.error('"{0}" is not a valid console number'.format(
                action.props["consoleNumber"]))

    def sendBeepCommand(self, action):
        """ Callback for sendBeepCommand """
        dev = indigo.devices[action.deviceId]
        if not action.props.get("consoleNumber", False):
            log.error("{0} not configured".format(action.pluginTypeId))
            return

        log.debug('sendBeepCommand called to send {0} to device "{1}" '
                  'console {2}'.format(action.props["beepCommand"], dev.name,
                                       action.props["consoleNumber"]))
        try:
            c = self.plugin.make_connection(dev.pluginProps["url"])
            CM = c.jomnilinkII.MessageTypes.CommandMessage
            console = int(action.props["consoleNumber"])
            beep = action.props["beepCommand"]
            if beep == "beepOff":
                beep_code = 0
            elif beep == "beepOn":
                beep_code = 1
            else:  # beep will be beepN with N between 1 and 5
                beep_code = int(beep[-1]) + 1

            c.omni.controllerCommand(CM.CMD_CONSOLE_BEEP, beep_code, console)
        except (Py4JError, ConnectionError):
            log.error("Error sending beep command to Omni Controller")
            log.debug("", exc_info=True)
        except ValueError:
            log.error("{0} is not a valid console number or "
                      "{1} is not a valid beep command".format(
                          action.props["consoleNumber"],
                          action.props["beepCommand"]))

    # ----- Write Info on connected controllers to log ----- #

    def say_system_information(self, r, connection, say):
        omni = connection.omni
        info = omni.reqSystemInformation()
        model, firmware = self.decode_system_info(info)
        say("Model:", model)
        say("Firmware version:", firmware)
        say("Phone number:", info.getPhone())

        status = omni.reqSystemStatus()
        self.say_system_time(status, say)
        say("Battery reading:", status.getBatteryReading())
        if status.getAlarms():
            areas = ", ".join((str(key) for key in status.getAlarms().keys()))
        else:
            areas = "None"
        say("Areas in alarm:", areas)

        formats = omni.reqSystemFormats()

        say("Temperature Format:",
            "F" if formats.getTempFormat() == 1 else "C")
        say("Time Format:",
            "12 hour" if formats.getTimeformat() == 1 else "24 hour")
        say("Date Format:",
            "MMDD" if formats.getDateFormat() == 1 else "DDMM")

    def say_system_time(self, status, say):
        if not status.isTimeDateValid():
            say("System Time: not set")
        else:
            dt = datetime(2000 + status.getYear(),  # year 2100 bug
                          status.getMonth(),
                          status.getDay(),
                          status.getHour(),
                          status.getMinute(),
                          status.getSecond())
            say("System Date:", dt.strftime("%x"))
            say("System Time:", dt.strftime("%X"))
            say("Daylight Savings:", status.isDaylightSavings())
            say("Day of week:", status.getDayOfWeek())
            say("Sunrise:", time(status.getSunriseHour(),
                                 status.getSunriseMinute()).strftime("%X"))
            say("Sunset:", time(status.getSunsetHour(),
                                status.getSunsetMinute()).strftime("%X"))

    def say_system_troubles(self, r, connection, say):
        omni = connection.omni
        system_troubles = omni.reqSystemTroubles()
        trouble_states = self.decode_troubles(system_troubles)
        troubles = [k for k, v in trouble_states.items() if v]
        say(*troubles if troubles else ["None"])

    def say_system_capacities(self, r, connection, say):
        omni = connection.omni
        M = connection.jomnilinkII.Message

        say("Max zones:",
            omni.reqObjectTypeCapacities(M.OBJ_TYPE_ZONE).getCapacity())
        say("Max units:",
            omni.reqObjectTypeCapacities(M.OBJ_TYPE_UNIT).getCapacity())
        say("Max areas:",
            omni.reqObjectTypeCapacities(M.OBJ_TYPE_AREA).getCapacity())
        say("Max buttons:",
            omni.reqObjectTypeCapacities(M.OBJ_TYPE_BUTTON).getCapacity())
        say("Max codes:",
            omni.reqObjectTypeCapacities(M.OBJ_TYPE_CODE).getCapacity())
        say("Max thermostats:",
            omni.reqObjectTypeCapacities(M.OBJ_TYPE_THERMO).getCapacity())
        say("Max messages:",
            omni.reqObjectTypeCapacities(M.OBJ_TYPE_MESG).getCapacity())
        say("Max audio zones:",
            omni.reqObjectTypeCapacities(M.OBJ_TYPE_AUDIO_ZONE).getCapacity())
        say("Max audio sources:",
            omni.reqObjectTypeCapacities(
                M.OBJ_TYPE_AUDIO_SOURCE).getCapacity())

    def say_event_log(self, r, connection, say):
        omni = connection.omni
        M = connection.jomnilinkII.Message
        self.say_event_log_entries(omni, M, 20, say)

    def say_event_log_entries(self, omni, M, limit, say):
        num = 0
        count = 0
        while True:
            m = omni.uploadEventLogData(num, -1)
            if (m.getMessageType() != M.MESG_TYPE_EVENT_LOG_DATA or
                    count > limit):
                break
            self.say_event_log_entry(m, say)
            num = m.getEventNumber()
            count += 1

    def say_event_log_entry(self, m, say):
        time_format = "%b %d %X   "
        if m.isTimeDataValid():
            time = datetime(
                # the 2016 is not printed (but it is a leap year)
                2016, m.getMonth(), m.getDay(), m.getHour(),
                m.getMinute()).strftime(time_format)
        else:
            width = len(datetime.now().strftime(time_format))
            time = "{{0:<{0}}}".format(width).format("Unknown")

        event, pn1, pn2 = self.events.get(m.getEventType(),
                                          ("Unknown", "Unused", "Unused"))
        pnames = [pn1, pn2]
        pvals = [self.modify_parameter(pn1, m.getParameter1()),
                 self.modify_parameter(pn2, m.getParameter2())]
        tups = [(pn, p) for pn, p in zip(pnames, pvals)
                if pn != "Unused"]

        width = max([len(e) for e, _, _ in self.events.values()])
        event = "{{0:<{0}}} ".format(width).format(event)

        params = ["{0}: {1}".format(pn, p) for pn, p in tups]
        params = "".join(["{0:<20}".format(p) for p in params])
        say(time + event + params)

    events = {
        4: ("Bypass", "User", "Zone"),
        5: ("Restore", "User", "Zone"),
        6: ("All Zones Restored", "User", "Area"),

        48 + 0: ("Disarm", "User", "Unused"),
        48 + 1: ("Arm Home", "User", "Unused"),
        48 + 2: ("Arm Sleep", "User", "Unused"),
        48 + 3: ("Arm Away", "User", "Unused"),
        48 + 4: ("Arm Vacation", "User", "Unused"),
        48 + 5: ("Arm Party", "User", "Unused"),
        48 + 6: ("Arm Special", "User", "Unused"),

        128: ("Zone Tripped", "Unused", "Zone"),
        129: ("Zone Trouble", "Unused", "Zone"),
        130: ("Remote Phone Access", "User", "Unused"),
        131: ("Remote Phone Lockout", "Unused", "Unused"),
        133: ("Trouble Cleared", "Unused", "Zone"),
        134: ("PC Access", "User", "Unused"),
        135: ("Alarm Activated", "Type", "Area"),
        136: ("Alarm Reset", "Type", "Area"),

        137: ("System Reset", "Unused", "Unused"),
        138: ("Message Logged", "Unused", "Message Number"),
        139: ("Zone Shut Down", "Unused", "Zone"),
        140: ("Access Granted", "User Number", "Reader"),
        141: ("Access Denied", "User Number", "Reader"),
        }

    special_user_codes = {
        251: "Duress code",
        252: "Keyswitch",
        253: "Quick arm",
        254: "PC Access",
        255: "Programmed",
        }

    alarm_types = {
        1: "Burglary",
        2: "Fire",
        3: "Gas",
        4: "Auxiliary",
        5: "Freeze",
        6: "Water",
        7: "Duress",
        8: "Temperature",
        }

    def modify_parameter(self, pname, p):
        if pname == "User":
            return self.special_user_codes.get(p, p)
        elif pname == "Area":
            return "All" if p == 0 else p
        elif pname == "Type":
            return self.alarm_types.get(p, "Unknown")
        return p

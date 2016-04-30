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
from datetime import time, datetime
from distutils.version import StrictVersion
import logging

import indigo
from py4j.protocol import Py4JError

import extensions
from properties import ControllerProps, ControllerStatus, AreaStatus

log = logging.getLogger(__name__)

_VERSION = "0.5.0"

# to do -- update the battery reading periodically (like once a day)
# action - set time in controller automatically
# to do - UIDisplayStateId should be based on troubles not connection
# action - acknowledge troubles


class ControllerExtension(extensions.DeviceMixin, extensions.PluginExtension):
    """Omni plugin extension for Controller devices """
    def __init__(self):
        self.type_ids = {"device": ["omniControllerDevice"],
                         "action": ["enableConsoleBeeper",
                                    "disableConsoleBeeper",
                                    "sendBeepCommand"],
                         "event": ["phoneLineDead", "phoneLineRing",
                                   "phoneLineOffHook", "phoneLineOnHook",
                                   "ACPowerOff", "ACPowerOn",
                                   "batteryLow", "batteryOK",
                                   "digitalCommunicatorModuleTrouble",
                                   "digitalCommunicatorModuleOK",
                                   "energyCostLow", "energyCostMid",
                                   "energyCostHigh", "energyCostCritical",
                                   "alarm"]}
        self.callbacks = {
            "generateConsoleList": self.generateConsoleList,
            "enableConsoleBeeper": self.enableDisableConsoleBeeper,
            "disableConsoleBeeper": self.enableDisableConsoleBeeper,
            "sendBeepCommand": self.sendBeepCommand,
            "generateAlarmTypeList": self.generateAlarmTypeList,
            "controllerIdChanged": self.controllerIdChanged
        }

        extensions.DeviceMixin.__init__(self, ControllerInfo, log)

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
        props["number"] = 1
        device.replacePluginPropsOnServer(props)

    def update(self):
        # periodically inquire about battery reading
        pass

    # ----- Callbacks from OMNI Status and events ----- #

    def status_notification(self, connection, status_msg):
        Message = connection.jomnilinkII.Message
        if status_msg.getStatusType() != Message.OBJ_TYPE_AREA:
            return

        status = status_msg.getStatuses()[0]
        info = self.info(connection.address)
        existing_alarms = info.get_alarm_set()
        info.update_alarm(status)

        new_alarms = info.get_alarm_set().difference(existing_alarms)
        if new_alarms:
            self.run_triggers_on_new_alarms(connection, new_alarms)

    def run_triggers_on_new_alarms(self, connection, alarms):
        log.debug("Controller at {0} has alarm: {1}".format(
            connection.address, ", ".join(list(alarms))))

        for dev in self.devices_from_address(connection.address):
            triggers = self.triggers[dev.id]
            for t in triggers["alarm"]:
                trig_alarms = set(indigo.triggers[t].pluginProps["alarmTypes"])
                if alarms.intersection(trig_alarms):
                    indigo.trigger.execute(t)

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
        for dev in self.devices_from_address(connection.address):
            triggers = self.triggers[dev.id]
            log.debug('Received "other event" notification for device '
                      "{0}".format(dev.id))
            try:
                notifications = other_event_msg.getNotifications()
                for n in notifications:
                    log.debug("Notification code: " + hex(n))
                    if n & self.notification_mask == self.notification_value:
                        event_num = n & self.event_mask
                        if event_num in self.event_types:
                            event_type = self.event_types[event_num]
                            log.debug("Processing {0} event for "
                                      "device {1}".format(event_type, dev.id))
                            for t in triggers[event_type]:
                                indigo.trigger.execute(t)
            except Py4JError:
                log.error("Unable to decode event notification", exc_info=True)

            self.update_device_status(dev)

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

        with extensions.comm_error_logging(log):
            c = self.plugin.make_connection(device.pluginProps["address"])
            M = c.jomnilinkII.Message
            count = c.omni.reqObjectTypeCapacities(
                M.OBJ_TYPE_CONSOLE).getCapacity()
            results = results + [(str(i), "Keypad {0}".format(i))
                                 for i in range(1, count + 1)]
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

        return (not errors, values, errors)

    # ----- Action Item Callbacks ----- #

    def enableDisableConsoleBeeper(self, action):
        """ Callback for enableConsoleBeeper and disableConsoleBeeper. """
        if (action.deviceId not in indigo.devices or
                not action.props.get("consoleNumber", False)):
            log.error("{0} not configured".format(action.pluginTypeId))
            return
        dev = indigo.devices[action.deviceId]
        log.debug('{0} called for device "{1}" console {2}'.format(
            action.pluginTypeId, dev.name, action.props["consoleNumber"]))

        enable = 1 if action.pluginTypeId == "enableConsoleBeeper" else 0
        try:
            with extensions.comm_error_logging(log):
                c = self.plugin.make_connection(dev.pluginProps["address"])
                CM = c.jomnilinkII.MessageTypes.CommandMessage
                console = int(action.props["consoleNumber"])
                c.omni.controllerCommand(CM.CMD_CONSOLE_ENABLE_DISABLE_BEEPER,
                                         enable, console)
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
            with extensions.comm_error_logging(log):
                c = self.plugin.make_connection(dev.pluginProps["address"])
                CM = c.jomnilinkII.MessageTypes.CommandMessage
                console = int(action.props["consoleNumber"])
                beep = action.props["beepCommand"]
                if beep == "beepOff":
                    beep_code = 0
                elif beep == "beepOn":
                    beep_code = 1
                else:  # beep will be beepN with N between 1 and 5
                    beep_code = int(beep[-1]) + 1

                c.omni.controllerCommand(CM.CMD_CONSOLE_BEEP, beep_code,
                                         console)
        except ValueError:
            log.error("{0} is not a valid console number or "
                      "{1} is not a valid beep command".format(
                          action.props["consoleNumber"],
                          action.props["beepCommand"]))

    # ----- Event Config UI ----- #

    def controllerIdChanged(self, values, type_id, event_id):
        """ If this doesn't exist, generateAlarmTypeList won't get called. """
        return values

    def generateAlarmTypeList(self, filter, values, type_id, event_id):
        """ Generate list of possible alarms, which will be different
        for Omni and Lumina controllers.
        """
        log.debug("generateAlarmTypeList called, {0}, {1}, {2}, {3}".format(
            filter, values, type_id, event_id))
        results = []
        dev_id = int(values.get("controllerId", 0))
        if dev_id:
            device = indigo.devices[dev_id]
            with extensions.comm_error_logging(log):
                info = self.info(device.pluginProps["address"])
                results = zip(AreaStatus.alarm_names, AreaStatus.alarm_names)
                if info.props[1].base_model == "Lumina":
                    # Lumina only has freeze, water, temp
                    results = [results[4], results[5], results[7]]

        return results

    def validateEventConfigUi(self, values, type_id, event_id):
        errors = indigo.Dict()
        if not values.get("controllerId", 0):
            errors["controllerId"] = "Please select a controller device"

        if type_id == "alarm" and not values.get("alarmTypes", []):
            errors["alarmTypes"] = ("Please select one or more alarm "
                                    "types to monitor")
        return (not errors, values, errors)


class ControllerInfo(extensions.Info):
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
    reports = ["System Information", "System Troubles", "System Capacities",
               "Event Log"]

    def __init__(self, connection):
        """ ControllerInfo constructor. Query an Omni controller for its status
        and decipher the results.
        See SystemInformation.java, SystemStatus.java
        and SystemTroubles.java for explanations of the data coming from
        jomnilinkII.
        """
        self.connection = connection
        self.props = {1: ControllerProps(connection)}

        # key is area, value is list of alarm types currently active
        self.alarms = {}

        self.update_alarms()

    def update_alarms(self):
        Message = self.connection.jomnilinkII.Message
        ObjectProps = self.connection.jomnilinkII.MessageTypes.ObjectProperties
        objnum = 0
        while True:
            m = self.connection.omni.reqObjectProperties(
                Message.OBJ_TYPE_AREA, objnum, 1,
                ObjectProps.FILTER_1_NAMED_UNAMED, ObjectProps.FILTER_2_NONE,
                ObjectProps.FILTER_3_NONE)
            if m.getMessageType() != Message.MESG_TYPE_OBJ_PROP:
                break
            objnum = m.getNumber()
            if m.isEnabled():
                self.update_alarm(m)

    def update_alarm(self, m):
        self.alarms[m.getNumber()] = AreaStatus.decode_alarms(m.getAlarms())

    def get_alarm_set(self):
        results = set()
        for alarms in self.alarms.values():
            results = results.union(set(alarms))
        return results

    def number_and_status_from_notification(self, status_msg):
        return None, None

    def fetch_status(self, objnum=1):
        """ Given the number of a controller (which is always 1!),
        find out its current status and return a ControllerStatus object.
        May raise ConnectionError or Py4JavaError if there is no valid
        connection or a network error.
        """
        return ControllerStatus(self.connection)

    # ----- Write Info on connected controller to log ----- #

    def report(self, report_name, say):
        reportmap = {"System Information": self.system_information_report,
                     "System Troubles": self.system_troubles_report,
                     "System Capacities": self.system_capacities_report,
                     "Event Log": self.event_log_report}
        if report_name in reportmap:
            reportmap[report_name](say)

    def system_information_report(self, say):
        omni = self.connection.omni
        props = self.props[1]

        say("Model:", props.model)
        say("Firmware version:", props.firmware)
        say("Phone number:", omni.reqSystemInformation().getPhone())

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

    def system_troubles_report(self, say):
        omni = self.connection.omni
        cs = self.fetch_status()
        troubles = [k for k, v in cs.troubles.items() if v]
        say(*troubles if troubles else ["None"])

    def system_capacities_report(self, say):
        omni = self.connection.omni
        M = self.connection.jomnilinkII.Message

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
        say("Max consoles:",
            omni.reqObjectTypeCapacities(M.OBJ_TYPE_CONSOLE).getCapacity())
        say("Max thermostats:",
            omni.reqObjectTypeCapacities(M.OBJ_TYPE_THERMO).getCapacity())
        say("Max messages:",
            omni.reqObjectTypeCapacities(M.OBJ_TYPE_MESG).getCapacity())
        say("Max audio zones:",
            omni.reqObjectTypeCapacities(M.OBJ_TYPE_AUDIO_ZONE).getCapacity())
        say("Max audio sources:",
            omni.reqObjectTypeCapacities(
                M.OBJ_TYPE_AUDIO_SOURCE).getCapacity())

    def event_log_report(self, say):
        omni = self.connection.omni
        M = self.connection.jomnilinkII.Message
        self.event_log_entries(omni, M, 20, say)

    def event_log_entries(self, omni, M, limit, say):
        num = 0
        count = 0
        while True:
            m = omni.uploadEventLogData(num, -1)
            if (m.getMessageType() != M.MESG_TYPE_EVENT_LOG_DATA or
                    count > limit):
                break
            self.event_log_entry(m, say)
            num = m.getEventNumber()
            count += 1

    def event_log_entry(self, m, say):
        time_format = "%b %d %X   "
        if m.isTimeDataValid():
            time = datetime(
                # the 2016 is not printed (but it is a leap year)
                2016, m.getMonth(), m.getDay(), m.getHour(),
                m.getMinute()).strftime(time_format)
        else:
            width = len(datetime.now().strftime(time_format))
            time = "{{0:<{0}}}".format(width).format("Unknown")

        etype = m.getEventType()
        if etype in self.events:
            event, pn1, pn2 = self.events[etype]
        else:
            model = self.props[1].base_model
            event, pn1, pn2 = self.modes[model].get(
                etype, ("Unknown", "Unused", "Unused"))

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

        128: ("Zone Tripped", "Unused", "Zone"),
        129: ("Zone Trouble", "Unused", "Zone"),
        130: ("Remote Phone Access", "User", "Unused"),
        131: ("Remote Phone Lockout", "Unused", "Unused"),
        132: ("Auto Bypass", "Unused", "Zone"),
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

    modes = {"Omni": {48 + 0: ("Disarm", "User", "Unused"),
                      48 + 1: ("Arm Day", "User", "Unused"),
                      48 + 2: ("Arm Night", "User", "Unused"),
                      48 + 3: ("Arm Away", "User", "Unused"),
                      48 + 4: ("Arm Vacation", "User", "Unused"),
                      48 + 5: ("Arm Day Instant", "User", "Unused"),
                      48 + 6: ("Arm Night Delayed", "User", "Unused")},
             "Lumina": {48 + 1: ("Set Home Mode", "User", "Unused"),
                        48 + 2: ("Set Sleep Mode", "User", "Unused"),
                        48 + 3: ("Set Away Mode", "User", "Unused"),
                        48 + 4: ("Set Vacation Mode", "User", "Unused"),
                        48 + 5: ("Set Party Mode", "User", "Unused"),
                        48 + 6: ("Set Special Mode", "User", "Unused")}}

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

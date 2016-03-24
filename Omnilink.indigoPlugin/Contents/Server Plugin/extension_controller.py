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
from collections import namedtuple
from distutils.version import StrictVersion
import logging

import indigo
from py4j.protocol import Py4JError

import extensions
from extensions import ConnectionError

log = logging.getLogger(__name__)

_VERSION = "0.2.0"

# to do -- update the battery reading periodically (like once a day)
# action - console beepers enable/disable/beep n times
# action - set time in controller
# action - read event log
# action - query all capabilities and dump to log
# to do - UIDisplayStateId should be based on troubles not connection
# action - acknowledge troubles
# to do - event notifications


class ControllerExtension(extensions.PluginExtension):
    """Omni plugin extension for Controller devices """
    def __init__(self):
        self.type_ids = {"device": ["omniControllerDevice"],
                         "action": ["checkSecurityCode"],
                         "event": []}
        self.devices = []
        self.callbacks = {
            "writeControllerInfoToLog": self.writeControllerInfoToLog,
            "checkSecurityCode": self.checkSecurityCode
        }
        self.controller_info = {}

    # ----- Device Start and Stop Methods ----- #

    def deviceStartComm(self, device):
        """ start an omniControllerDevice. Query the Omni system and set
        the states of the indigo device. """
        log.debug("Starting device {0}".format(device.id))
        if device not in self.devices:
            self.devices.append(device)
            self.update_device_version(device)
            self.update_device_status(device)

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
        connection = self.plugin.make_connection(device.pluginProps)
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
              37: "HAI Lumina Pro"}

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

        status = connection.omni.reqSystemStatus()
        battery_reading = status.getBatteryReading()

        troubles = connection.omni.reqSystemTroubles()
        trouble_states = {}
        for t in self.trouble_names:
            trouble_states[t] = False
        for t in troubles.getTroubles():
            trouble_states[self.trouble_names[t - 1]] = True

        return namedtuple(
            "Info", ["model", "firmware", "battery_reading", "troubles"])(
                model, firmware, battery_reading, trouble_states)

    def deviceStopComm(self, device):
        if device in self.devices:
            self.devices.remove(device)

    # ----- Device creation ----- #

    def getDeviceList(self, props, dev_ids):
        """ Return list of devices this extension can create """
        return [("omniControllerDevice", "Controller")]

    def createDevices(self, props, prefix, dev_ids):
        """ Automatically create a controller device, unless there is one
        already.
        """
        for dev_id in dev_ids:
            if indigo.devices[dev_id].deviceTypeId == "omniControllerDevice":
                return
        log.debug("Creating controller device")

        props["deviceVersion"] = _VERSION
        kwargs = {"props": props,
                  "deviceTypeId": "omniControllerDevice"}
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

    def event_notification(self, connection, other_event_msg):
        connection_props = self.plugin.props_from_connection(connection)

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
                dev.updateStateOnServer("connected", False)
                dev.setErrorStateOnServer("not connected")

    # ----- Action Item Config UI ----- #

    def getActionConfigUiValues(self, values, type_id, device_id):
        """ called by the Indigo UI before the Action configuration dialog
        is shown to the user.
        """
        errors = indigo.Dict()
        values["device_id"] = device_id
        return (values, errors)

    def validateActionConfigUi(self, values, type_id, action_id):
        """ called by the Indigo UI to validate the values dictionary
        for the Action user interface dialog
        """
        log.debug("Action Validation called for %s" % type_id)
        errors = indigo.Dict()

        if (StrictVersion(values.get("actionVersion", "0.0")) <
                StrictVersion(_VERSION)):
            values["actionVersion"] = _VERSION

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

        if not self.is_valid_code(code):
            log.error("checkSecurityCode asked to validate "
                      "'{0}' which is not between 0001 and 9999".format(code))
        elif not self.is_valid_area(area):
            log.error("checkSecurityCode asked to validate code in area "
                      "{0} which is not between 1 and 255".format(area))
        else:
            try:
                c = self.plugin.make_connection(dev.pluginProps)
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

            except Py4JError, ConnectionError:
                log.error("Error communicating with Omni Controller")
                log.debug("", exc_info=True)

        self.update_last_checked_code(dev, code=code, area=area,
                                      authority="Error")

    # ----- Menu Item Callbacks ----- #

    def writeControllerInfoToLog(self):
        """ Callback for the "Write information on connected OMNI Controllers
        to Log" menu item.
        """
        first = True
        for c in self.plugin.connections.values():
            if not c.is_connected():
                msg = "OMNI Controller at {0} is not connected ".format(c.ip)
                if c.javaproc is None:
                    msg = msg + ("because the Java subprocess could not be "
                                 "started.")
                elif c.gateway is None:
                    msg = msg + ("because the gateway between Python and Java "
                                 "could not be started.")
                else:
                    msg = msg + ("because it did not respond, or because the "
                                 "IP address, port or encryption keys are "
                                 "not correct.")
                self.log(msg)
            else:
                if first:
                    first = False
                else:
                    self.log("-" * 80)
                try:
                    self.log_everything_we_know_about(c)
                except (ConnectionError, Py4JError):
                    log.error("Error communicating with Omni system")
                    log.debug("", exc_info=True)

    def log_everything_we_know_about(self, c):
        self.log("Omni Controller at {0}:".format(c.ip))
        M = c.jomnilinkII.Message
        OP = c.jomnilinkII.MessageTypes.ObjectProperties
        omni = c.omni

        self.log(omni.reqSystemInformation().toString())
        self.log(omni.reqSystemStatus().toString())
        self.log(omni.reqSystemFormats().toString())

        self.log("System Troubles:", *omni.reqSystemTroubles().getTroubles())
        self.log("System Features:", *omni.reqSystemFeatures().getFeatures())

        self.log(
            "Max zones:",
            omni.reqObjectTypeCapacities(M.OBJ_TYPE_ZONE).getCapacity())

        self.log(
            "Max units:",
            omni.reqObjectTypeCapacities(M.OBJ_TYPE_UNIT).getCapacity())

        self.log(
            "Max areas:",
            omni.reqObjectTypeCapacities(M.OBJ_TYPE_AREA).getCapacity())

        self.log(
            "Max buttons:",
            omni.reqObjectTypeCapacities(M.OBJ_TYPE_BUTTON).getCapacity())

        self.log(
            "Max codes:",
            omni.reqObjectTypeCapacities(M.OBJ_TYPE_CODE).getCapacity())

        self.log(
            "Max thermostats:",
            omni.reqObjectTypeCapacities(M.OBJ_TYPE_THERMO).getCapacity())

        max_messages = omni.reqObjectTypeCapacities(
            M.OBJ_TYPE_MESG).getCapacity()
        self.log("Max messages:", max_messages)

        max_audio_zones = omni.reqObjectTypeCapacities(
            M.OBJ_TYPE_AUDIO_ZONE).getCapacity()
        self.log("Max audio zones:", max_audio_zones)

        max_audio_sources = omni.reqObjectTypeCapacities(
            M.OBJ_TYPE_AUDIO_SOURCE).getCapacity()
        self.log("Max audio sources:", max_audio_sources)

        self.query_and_print(omni, M.OBJ_TYPE_ZONE, M.MESG_TYPE_OBJ_PROP,
                             OP.FILTER_1_NAMED,
                             OP.FILTER_2_AREA_ALL,
                             OP.FILTER_3_ANY_LOAD)

        self.query_and_print(omni, M.OBJ_TYPE_AREA, M.MESG_TYPE_OBJ_PROP,
                             OP.FILTER_1_NAMED_UNAMED,
                             OP.FILTER_2_NONE,
                             OP.FILTER_3_NONE)

        self.query_and_print(omni, M.OBJ_TYPE_UNIT, M.MESG_TYPE_OBJ_PROP,
                             OP.FILTER_1_NAMED,
                             OP.FILTER_2_AREA_ALL,
                             OP.FILTER_3_ANY_LOAD)

        self.query_and_print(omni, M.OBJ_TYPE_BUTTON, M.MESG_TYPE_OBJ_PROP,
                             OP.FILTER_1_NAMED,
                             OP.FILTER_2_AREA_ALL,
                             OP.FILTER_3_NONE)

        self.query_and_print(omni, M.OBJ_TYPE_CODE, M.MESG_TYPE_OBJ_PROP,
                             OP.FILTER_1_NAMED,
                             OP.FILTER_2_AREA_ALL,
                             OP.FILTER_3_NONE)

        self.query_and_print(omni, M.OBJ_TYPE_THERMO, M.MESG_TYPE_OBJ_PROP,
                             OP.FILTER_1_NAMED,
                             OP.FILTER_2_AREA_ALL,
                             OP.FILTER_3_NONE)

        self.query_and_print(omni, M.OBJ_TYPE_AUX_SENSOR, M.MESG_TYPE_OBJ_PROP,
                             OP.FILTER_1_NAMED,
                             OP.FILTER_2_AREA_ALL,
                             OP.FILTER_3_NONE)

        self.query_and_print(omni, M.OBJ_TYPE_MESG, M.MESG_TYPE_OBJ_PROP,
                             OP.FILTER_1_NAMED,
                             OP.FILTER_2_AREA_ALL,
                             OP.FILTER_3_NONE)

        status = omni.reqObjectStatus(M.OBJ_TYPE_AUDIO_ZONE, 1,
                                      max_audio_zones)
        statuses = status.getStatuses()
        for s in statuses:
            self.log(s.toString())

        for as_index in range(1, max_audio_sources):
            pos = 0
            while True:
                m = omni.reqAudioSourceStatus(as_index, pos)
                if m.getMessageType() != M.MESG_TYPE_AUDIO_SOURCE_STATUS:
                    break
                self.log(m.toString())
                pos = m.getPosition()

        num = 0
        count = 0
        while True:
            m = omni.uploadEventLogData(num, 1)
            if (m.getMessageType() != M.MESG_TYPE_EVENT_LOG_DATA or
                    count > 10):
                break
            self.log(m.toString())
            num = m.getEventNumber()
            count += 1

        self.log(omni.uploadNames(M.OBJ_TYPE_UNIT, 0).toString())

    def query_and_print(self, omni, objtype, mtype, filter1, filter2, filter3):
        objnum = 0
        while True:
            m = omni.reqObjectProperties(objtype, objnum, 1, filter1, filter2,
                                         filter3)
            if m.getMessageType() != mtype:
                break
            self.log(m.toString())
            objnum = m.getNumber()
            status = omni.reqObjectStatus(objtype, objnum, objnum)
            statuses = status.getStatuses()
            for s in statuses:
                self.log(s.toString())

    def log(self, *args):
        indigo.server.log(" ".join([unicode(arg) for arg in args]))

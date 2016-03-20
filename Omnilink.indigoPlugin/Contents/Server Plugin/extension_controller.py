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
import logging

import indigo
from py4j.protocol import Py4JError

import extensions
from extensions import ConnectionError

log = logging.getLogger(__name__)

_VERSION = "0.1.0"

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
                         "action": [],
                         "event": []}
        self.devices = []
        self.callbacks = {}
        self.controller_info = {}

    # ----- Device Start and Stop Methods ----- #

    def deviceStartComm(self, device):
        """ start an omniControllerDevice. Query the Omni system and set
        the states of the indigo device. """
        if device not in self.devices:
            self.devices.append(device)
        self.update_device_status(device)

    def update_device_status(self, device):
        connection = self.plugin.make_connection(device.pluginProps)
        try:
            info = self.get_controller_info(connection)
            device.updateStateOnServer("connected", True)
            device.updateStateOnServer("model", info.model)
            device.updateStateOnServer("firmwareVersion", info.firmware)
            device.updateStateOnServer("batteryReading", info.battery_reading)
            for t, value in info.troubles.items():
                device.updateStateOnServer(t, value)
            device.setErrorStateOnServer(None)

        except (Py4JError, ConnectionError):
            log.error("Could not get status of Omni Controller")
            log.debug("", exc_info=True)
            device.updateStateOnServer("connected", False)
            device.setErrorStateOnServer("not connected")

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

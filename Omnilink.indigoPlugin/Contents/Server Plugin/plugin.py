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

"""Leviton/HAI Omni plugin for IndigoServer"""
from __future__ import print_function
from __future__ import unicode_literals

from distutils.version import StrictVersion
import glob
import imp
import logging
import os
import re
import threading

import indigo
import py4j
from py4j.protocol import Py4JError
from termapp_server import start_shell_thread

import connection
from connection import Connection, ConnectionError
import extensions

_SLEEP = 0.1

log = logging.getLogger(__name__)
log_omni = logging.getLogger(__name__ + ".jomnilinkII")

# TODO - Make it possible to change the ports used for Py4J
# TODO - configure sleep time waiting for java process
# TODO - what if the dialog is brought up with pre-existing devices but
#      the encryption key has changed, user fixes it in dialog, we need
#      to fix it in all devices in group


class Plugin(indigo.PluginBase):
    """Leviton/HAI Omni plugin class for IndigoServer"""

    # ----- plugin framework ----- #

    def __init__(self, plugin_id, display_name, version, prefs):
        indigo.PluginBase.__init__(self, plugin_id, display_name,
                                   version, prefs)

        self.debug = prefs.get("showDebugInfo", False)
        self.debug_omni = prefs.get("showJomnilinkIIDebugInfo", False)
        self.configure_logging()

        if (StrictVersion(prefs.get("configVersion", "0.0")) <
                StrictVersion(version)):
            log.debug("Updating config version to " + version)
            prefs["configVersion"] = version
        self.VERSION = version
        self.connections = {}

        self.extensions = []
        self.type_ids_map = {"device": {},
                             "event": {},
                             "action": {}}
        self.status_callbacks = []
        self.event_callbacks = []
        self.disconnect_callbacks = []
        self.reconnect_callbacks = []

        self.load_extensions()

    def startup(self):
        log.debug("Startup called")
        stdout, stderr = Connection.startup(timeout=5)
        self.start_omni_logging(stdout, stderr)

    def shutdown(self):
        log.debug("Shutdown called")
        Connection.shutdown()

    def update(self):
        for connection in self.connections.values():
            connection.update()
        for ext in self.extensions:
            ext.update()

    def runConcurrentThread(self):
        log.debug("Concurrent thread starting")
        try:
            while True:
                self.update()
                self.sleep(_SLEEP)  # seconds
        except self.StopThread:
            log.debug("Concurrent thread stopping")

    def load_extensions(self):
        """ Look in the current directory (which Indigo sets to the
        Server Plugin directory before starting the plugin) for python
        files of the form extension_*.py. Import each one, and then
        call extend_plugin (see below) with each subclass of PluginExtension
        found during the import process.
        """
        extensions.PluginExtension.plugin = self
        extensions.PluginExtensionRegistrar.clear()

        directory = os.getcwd()
        files = glob.glob("extension_*.py")
        if files is not None:
            for item in files:
                log.debug("Importing " + item)
                name, ext = os.path.splitext(item)
                try:
                    file, filename, data = imp.find_module(name, [directory])
                    imp.load_module(name, file, filename, data)
                    self.configure_logger(logging.getLogger(name),
                                          prefix=name[len("extension_"):],
                                          propagate=False)
                except Exception:
                    log.error("Error while importing {0}".format(item),
                              exc_info=True)

        for cls in extensions.PluginExtensionRegistrar.registry:
            log.debug("Extending plugin with " + cls.__name__)
            self.extend_plugin(cls)

    def extend_plugin(self, cls):
        """ Given a subclass of PluginExtension, add its functionality to
        this plugin instance.

        See extensions.py for details.
        """
        extension = cls()
        self.extensions.append(extension)
        for name, func in extension.callbacks.items():
            if hasattr(self, name):
                log.error("Extension {0} redefined {1}".format(cls.__name__,
                                                               name))
            setattr(self, name, func)

        if extension.type_ids is not None:
            for thing, type_ids in extension.type_ids.items():
                for type_id in type_ids:
                    self.type_ids_map[thing][type_id] = extension

        self.status_callbacks.append(extension.status_notification)
        self.event_callbacks.append(extension.event_notification)
        self.disconnect_callbacks.append(extension.disconnect_notification)
        self.reconnect_callbacks.append(extension.reconnect_notification)

    # ----- Management of Connection objects ----- #

    def make_connection(self, params):
        """ Create a Connection object, and cache it in self.connections
        which is a dictionary of Connection objects indexed by the
        concatenation of the ip, port (as a string) and encoding.

        params - a dictionary containing the keys "ipAddress", "portNumber",
            "encryptionKey1" and "encryptionKey2"

        This will always return a Connection object, no exceptions.
        """
        key = self.make_connection_key(params)
        if self.is_connected(params):
            return self.connections[key]

        ip = params["ipAddress"]
        port = int(params["portNumber"])
        encoding = (params["encryptionKey1"] + "-" +
                    params["encryptionKey2"])

        c = Connection(ip, port, encoding,
                       status_callbacks=self.status_callbacks,
                       event_callbacks=self.event_callbacks,
                       disconnect_callbacks=self.disconnect_callbacks,
                       reconnect_callbacks=self.reconnect_callbacks)
        self.connections[key] = c
        return c

    def is_connected(self, params):
        """ Use this to find out of the connection you just tried to make
        worked. Don't count on it to tell you if the next thing you're going
        to do is going to work.
        """
        key = self.make_connection_key(params)
        return (key in self.connections and
                self.connections[key].is_connected())

    def make_connection_key(self, params):
        """ Make a key suitable for indexing a dictionary from a dictionary
        containing connection parameters. """
        ip = params["ipAddress"]
        port = params["portNumber"]
        encoding = (params["encryptionKey1"] + "-" +
                    params["encryptionKey2"])
        return ip + port + encoding

    def props_from_connection(self, connection):
        """ Get the connection key from a Connection object """
        return {"ipAddress": connection.ip,
                "portNumber": str(connection.port),
                "encryptionKey1": connection.encoding[:23],
                "encryptionKey2": connection.encoding[24:]}

    # ----- Logging Configuration ----- #

    def configure_logging(self):
        """ Set up the logging for this module, py4j, and jomnilinkII
        """
        self.configure_logger(log)
        self.configure_logger(logging.getLogger("connection"))
        self.configure_logger(logging.getLogger("termapp_server"))
        log_py4j = logging.getLogger("py4j")
        self.configure_logger(log_py4j, logging.WARNING, prefix="py4j")

        self.configure_logger(log_omni)
        self.set_omni_logging_level()

    def configure_logger(self, logger, level=logging.DEBUG, prefix="",
                         propagate=False):
        """ Create a Handler subclass for the logging module that uses the
        logging methods supplied to the plugin by Indigo. Prepend the thread
        name to the message if not in the main thread.
        """
        def make_handler(debugLog, errorLog, prefix=""):
            class NewHandler(logging.Handler):
                def emit(self, record):
                    try:
                        msg = self.format(record)
                        threadname = threading.current_thread().name
                        if threadname != "MainThread":
                            if "Dummy" in threadname:  # RunConcurrentThread
                                threadname = "Update"
                            elif "Thread" in threadname:  # py4j callback
                                threadname = "Notify"
                            msg = ("[{0}] {1}".format(threadname, msg))
                        if record.levelno < logging.WARNING:
                            debugLog(msg)
                        else:
                            errorLog(msg)
                    except Exception:
                        self.handleError(record)
            handler = NewHandler()
            if prefix:
                prefix = "[" + prefix + "] "
            handler.setFormatter(logging.Formatter(prefix + "%(message)s"))
            return handler

        logger.addHandler(make_handler(self.debugLog, self.errorLog,
                                       prefix))
        logger.setLevel(level)
        if propagate is not None:
            logger.propagate = propagate

    def set_omni_logging_level(self):
        """ Set the logging level for logging of the jomnilinkII library """
        if self.debug_omni:
            log_omni.setLevel(logging.DEBUG)
        else:
            log_omni.setLevel(logging.ERROR)

    def start_omni_logging(self, stdout, stderr):
        """ Connect the output pipes of our connection subprocess to threads
        that will read lines of output and log them. """
        if stdout is None:
            return
        t = threading.Thread(target=self.read_from_file_write_to_log,
                             name="Omni",
                             args=(log_omni, logging.DEBUG, stdout))
        t.setDaemon(True)
        t.start()
        t = threading.Thread(target=self.read_from_file_write_to_log,
                             name="Omni Error",
                             args=(log_omni, logging.ERROR, stderr))
        t.setDaemon(True)
        t.start()

    def read_from_file_write_to_log(self, logger, level, pipe):
        """ logging helper function to capture output from subprocess.
        """
        while True:
            line = pipe.readline()  # blocks here if no input
            if not line:            # EOF
                break
            logger.log(level, line.strip())

    # ----- Preferences UI ----- #

    def validatePrefsConfigUi(self, values):
        """ called by the Indigo UI to validate the values dictionary for
        the Plugin Preferences user interface dialog
        """
        errors = indigo.Dict()
        log.debug("Preferences Validation called")

        debug = values.get("showDebugInfo", False)
        if self.debug:
            if not debug:
                log.debug("Turning off debug logging")
        self.debug = debug
        log.debug("Debug logging is on")  # won't print if not self.debug

        self.debug_omni = values.get("showJomnilinkIIDebugInfo", False)
        self.set_omni_logging_level()
        return not errors, values, errors

    # ----- Device Factory UI ----- #

    def getDeviceFactoryUiValues(self, dev_ids):
        """ Called by the IndigoUI to initialize values for the Device
        Factory dialog. If the device group has already been created,
        dev_ids will contain a list of devices. If so, grab the pluginProps
        from one of them and get the connection parameters, and try
        to connect.
        """
        log.debug("Initializing Device Factory UI")
        values = indigo.Dict()
        if dev_ids:
            props = indigo.devices[dev_ids[0]].pluginProps
            for k in self.dialog_keys:
                values[k] = props.get(k, "")
        errors = self.checkConnectionParameters(values)
        if not errors:
            self.make_connection(values)
            if self.is_connected(values):
                values["isConnected"] = True
        return values, indigo.Dict()

    def validateDeviceFactoryUi(self, values, dev_ids):
        """ Called by the Indigo UI to check values for the Device
        Factory dialog, when the user closes it, and also by the
        callback for the Connect button (see below). This checks the
        syntax of the port number and encryption keys, and
        then tries to connect. """
        log.debug("Device Factory Config Validation called")
        errors = self.checkConnectionParameters(values)
        if not errors:
            self.make_connection(values)
            if not self.is_connected(values):
                log.error("Failed to connect to Omni controller")
                errors["showAlertText"] = (
                    "Unable to connect with your Omni system. Please recheck "
                    "the information from the Setup menu, as well as your "
                    "network cable and firmware version.")
        return not errors, values, errors

    def checkConnectionParameters(self, values):
        """ Check the syntax of the ipAddress, port and encryption keys
        in the values dictionary. Return a dictionary of error messages
        if problems are found.
        """
        errors = indigo.Dict()

        for key, tup in self.dialog_value_checks.items():
            is_valid, message = tup
            value = values.get(key, None)
            if value is None or not is_valid(self, value):
                errors[key] = message
        if not errors:
            values["portNumber"] = str(int(values["portNumber"]))
        return errors

    def is_valid_port_number(self, port):
        return (re.match(r"\d{1,5}", port) is not None and
                0 < int(port) < 65536)

    def is_valid_encryption_key(self, key):
        return re.match(r"^([\dA-F]{2}\-){7}[\dA-F]{2}$", key) is not None

    dialog_keys = ["ipAddress", "portNumber",
                   "encryptionKey1", "encryptionKey2"]

    dialog_value_checks = {
        "portNumber": (is_valid_port_number,
                       "Please enter the controller port number from the "
                       "Setup menu on your Omni system keypad."),
        "encryptionKey1": (is_valid_encryption_key,
                           "Please enter the encryption key part 1 from "
                           "the Setup menu on your Omni system keypad."),
        "encryptionKey2": (is_valid_encryption_key,
                           "Please enter the encryption key part 2 from "
                           "the Setup menu on your Omni system keypad.")}

    def closedDeviceFactoryUi(self, values, user_cancelled, dev_ids):
        """ Called by the Indigo UI when the Device Factory dialog is closed.
        """
        pass

    def makeConnection(self, values, dev_ids):
        """ Callback for the Connect button in the Device Factory dialog.
        Tries to connect based on the connection parameters, and sets the
        various error flags in the dialog if there are problems.
        """
        log.debug("makeConnection called")
        ok, values, errors = self.validateDeviceFactoryUi(values, dev_ids)
        for k in self.dialog_value_checks.keys():
            values[k + "Error"] = k in errors
        values["connectionError"] = "showAlertText" in errors

        values["error"] = (len(errors) != 0)
        values["isConnected"] = not values["error"]
        return values

    def getDeviceGroupList(self, filter, values, dev_ids):
        """ Callback for the list of device groups in the Device Factory
        dialog. Asks each plugin extension for the device types it supports.
        Builds a list of device types and sorts it.
        """
        log.debug("getDeviceGroupList called")

        results = []
        if ("isConnected" in values and values["isConnected"] and
                self.is_connected(values)):
            for ext in self.extensions:
                results.extend(ext.getDeviceList(values, dev_ids))

        return sorted(results, key=lambda tup: tup[1])

    def createDevices(self, values, dev_ids):
        """ Callback for the Create Devices button in the Device Factory
        dialog. For each selected device type in the deviceGroupList box
        in the dialog, call the appropriate extension and ask it to create
        devices.
        """
        for dev_type in values["deviceGroupList"]:
            ext = self.type_ids_map["device"][dev_type]
            props = {}
            for key in self.dialog_keys:
                props[key] = values[key]
            ext.createDevices(dev_type, props, values["prefix"], dev_ids)
        return values

    def removeDevices(self, values, dev_ids):
        """ Callback for the Remove Devices button in the Device Factory
        dialog. Deletes devices matching selection in the deviceGroupList
        box in the dialog. Extensions that want to know about that should
        implement deviceDeleted.
        """
        for dev_id in dev_ids:
            try:
                dev = indigo.devices[dev_id]
                if dev.deviceTypeId in values["deviceGroupList"]:
                    indigo.device.delete(dev)
            except:
                log.debug("Exception in removeDevices", exc_info=True)
        return values

    # ----- Menu Items ----- #

    def toggleDebugging(self):
        """ Called by the Indigo UI for the Toggle Debugging menu item. """
        if self.debug:
            log.debug("Turning off debug logging")
        self.debug = not self.debug
        log.debug("Turning on debug logging")  # won't print if !self.debug
        self.pluginPrefs["showDebugInfo"] = self.debug

    def toggleJomnilinkIIDebugging(self):
        """ Called by the Indigo UI for the Toggle Omni Network Comm
        Debugging menu item.
        """
        if self.debug_omni:
            log.debug("Turning off Omni Network Communication debug logging")
        else:
            log.debug("Turning on Omni Network Communication debug logging")
        self.debug_omni = not self.debug_omni
        self.pluginPrefs["showJomnilinkIIDebugInfo"] = self.debug_omni
        self.set_omni_logging_level()

    def startInteractiveInterpreter(self):
        """ Called by the Indigo UI for the Start Interactive Interpreter
        menu item.
        """
        log.debug("startInteractiveInterpreter called")
        namespace = globals().copy()
        namespace.update(locals())
        start_shell_thread(namespace, "", "OmniLink")

    # ----- Dispatch various calls to either extensions or PluginBase ----- #

    def getActionConfigUiValues(self, pluginProps, typeId, actionId):
        return self.dispatch("getActionConfigUiValues", "action", typeId,
                             pluginProps, typeId, actionId)

    def getDeviceConfigUiValues(self, pluginProps, typeId, devId):
        return self.dispatch("getDeviceConfigUiValues", "device", typeId,
                             pluginProps, typeId, devId)

    def getEventConfigUiValues(self, pluginProps, typeId, eventId):
        return self.dispatch("getEventConfigUiValues", "event", typeId,
                             pluginProps, typeId, eventId)

    def validateActionConfigUi(self, valuesDict, typeId, actionId):
        return self.dispatch("validateActionConfigUi", "action", typeId,
                             valuesDict, typeId, actionId)

    def validateEventConfigUi(self, valuesDict, typeId, eventId):
        return self.dispatch("validateEventConfigUi", "event", typeId,
                             valuesDict, typeId, eventId)

    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        return self.dispatch("validateDeviceConfigUi", "device", typeId,
                             valuesDict, typeId, devId)

    def closedActionConfigUi(self, valuesDict, userCancelled, typeId,
                             actionId):
        return self.dispatch("closedActionConfigUi", "action", typeId,
                             valuesDict, userCancelled, typeId, actionId)

    def closedEventConfigUi(self, valuesDict, userCancelled, typeId, eventId):
        return self.dispatch("closedEventConfigUi", "event", typeId,
                             valuesDict, userCancelled, typeId, eventId)

    def closedDeviceConfigUi(self, valuesDict, userCancelled, typeId, devId):
        return self.dispatch("closedDeviceConfigUi", "device", typeId,
                             valuesDict, userCancelled, typeId, devId)

    def deviceStartComm(self, dev):
        return self.dispatch("deviceStartComm", "device", dev.deviceTypeId,
                             dev)

    def deviceStopComm(self, dev):
        return self.dispatch("deviceStopComm", "device", dev.deviceTypeId,
                             dev)

    def deviceCreated(self, dev):
        return self.dispatch("deviceCreated", "device", dev.deviceTypeId,
                             dev)

    def deviceDeleted(self, dev):
        return self.dispatch("deviceDeleted", "device", dev.deviceTypeId,
                             dev)

    def deviceUpdated(self, origDev, newDev):
        return self.dispatch("deviceUpdated", "device", origDev.deviceTypeId,
                             origDev, newDev)

    def getDeviceStateList(self, dev):
        return self.dispatch("getDeviceStateList", "device", dev.deviceTypeId,
                             dev)

    def getDeviceDisplayStateId(self, dev):
        return self.dispatch("getDeviceDisplayStateId", "device",
                             dev.deviceTypeId,
                             dev)

    def didDeviceCommPropertyChange(self, origDev, newDev):
        return self.dispatch("didDeviceCommPropertyChange", "device",
                             origDev.deviceTypeId,
                             origDev, newDev)

    def actionControlGeneral(self, action, dev):
        return self.dispatch("actionControlGeneral", "device",
                             dev.deviceTypeId,
                             action, dev)

    def actionControlDimmerRelay(self, action, dev):
        return self.dispatch("actionControlDimmerRelay", "device",
                             dev.deviceTypeId,
                             action, dev)

    def actionControlSensor(self, action, dev):
        return self.dispatch("actionControlSensor", "device", dev.deviceTypeId,
                             action, dev)

    def actionControlSpeedControl(self, action, dev):
        return self.dispatch("actionControlSpeedControl", "device",
                             dev.deviceTypeId,
                             action, dev)

    def actionControlThermostat(self, action, dev):
        return self.dispatch("actionControlThermostat", "device",
                             dev.deviceTypeId,
                             action, dev)

    def actionControlIO(self, action, dev):
        return self.dispatch("actionControlIO", "device", dev.deviceTypeId,
                             action, dev)

    def actionControlSprinkler(self, action, dev):
        return self.dispatch("actionControlSprinkler", "device",
                             dev.deviceTypeId,
                             action, dev)

    def triggerStartProcessing(self, trigger):
        return self.dispatch("triggerStartProcessing", "event",
                             trigger.pluginTypeId,
                             trigger)

    def triggerStopProcessing(self, trigger):
        return self.dispatch("triggerStopProcessing", "event",
                             trigger.pluginTypeId,
                             trigger)

    def didTriggerProcessingPropertyChange(self, origTrigger, newTrigger):
        return self.dispatch("didTriggerProcessingPropertyChange", "event",
                             origTrigger.pluginTypeId,
                             origTrigger, newTrigger)

    def triggerCreated(self, trigger):
        return self.dispatch("triggerCreated", "event",
                             trigger.pluginTypeId,
                             trigger)

    def triggerUpdated(self, origTrigger, newTrigger):
        return self.dispatch("triggerUpdated", "event",
                             origTrigger.pluginTypeId,
                             origTrigger, newTrigger)

    def triggerDeleted(self, trigger):
        return self.dispatch("triggerDeleted", "event",
                             trigger.pluginTypeId,
                             trigger)

    def dispatch(self, name, selector, type_id, *args):
        if type_id in self.type_ids_map[selector]:
            ext = self.type_ids_map[selector][type_id]
            if hasattr(ext, name):
                return getattr(ext, name)(*args)
        else:
            log.debug("No matching plugin extension found for {0} {1} "
                      "method {2}".format(selector, type_id, name))

        if hasattr(indigo.PluginBase, name):
            return getattr(indigo.PluginBase, name)(self, *args)
        else:
            return None

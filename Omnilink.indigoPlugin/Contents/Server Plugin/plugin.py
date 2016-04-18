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
from keychain import KeyChain
import extensions

_SLEEP = 0.1

log = logging.getLogger(__name__)

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

        self.plugin_id = plugin_id
        self.debug = prefs.get("showDebugInfo", False)
        self.debug_omni = prefs.get("showJomnilinkIIDebugInfo", False)
        self.configure_logging()
        if (StrictVersion(prefs.get("configVersion", "0.0")) <
                StrictVersion(version)):
            log.debug("Updating config version to " + version)
            prefs["configVersion"] = version

        self.connections = {}
        self.keychain = KeyChain(plugin_id)

        self.extensions = []
        self.type_ids_map = {"device": {},
                             "event": {},
                             "action": {}}

        self.notifications = {"status": [],
                              "event": [],
                              "disconnect": [],
                              "reconnect": []}

        self.load_extensions()

    def startup(self):
        log.debug("Startup called")
        stdout, stderr = Connection.startup(timeout=5)
        self.start_omni_logging(stdout, stderr)

    def shutdown(self):
        log.debug("Shutdown called")
        Connection.shutdown()

    def update(self):
        for conn in self.connections.values():
            conn.update()
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

    # ----- This plugin has its own plugins ----- #

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
        ext = cls()
        self.extensions.append(ext)
        for name, func in ext.callbacks.items():
            if hasattr(self, name):
                log.error("Extension {0} redefined {1}".format(cls.__name__,
                                                               name))
            setattr(self, name, func)

        if ext.type_ids is not None:
            for thing, type_ids in ext.type_ids.items():
                for type_id in type_ids:
                    self.type_ids_map[thing][type_id] = ext

        for ntype in ["status", "event", "disconnect", "reconnect"]:
            method = ntype + "_notification"
            if hasattr(ext, method):
                self.notifications[ntype].append(getattr(ext, method))

    # ----- Management of Connection objects ----- #

    def make_connection(self, url, encKey1="", encKey2=""):

        """ Create a Connection object, and cache it in self.connections
        which is a dictionary of Connection objects indexed by ip:port

        params - a dictionary containing the keys "ipAddress", "portNumber".
            If "encryptionKey1" and "encryptionKey2" are present, they
            will be used, otherwise the encryption keys will be fetched
            from the keychain.

        This will always return a Connection object, no exceptions.
        """
        ip, port = self.split_url(url)

        if not encKey1:
            encKey1, encKey2 = self.keychain.get_keys(ip, port)
        if encKey1:
            encoding = encKey1 + "-" + encKey2
        else:
            encoding = ""

        if (url in self.connections and
                self.connections[url].encoding == encoding):
            return self.connections[url]

        c = Connection(ip, port, encoding, self.notifications)
        self.connections[url] = c
        return c

    def did_connection_succeed(self, params):
        """ Use this to find out if the connection you just tried to make
        worked. Don't count on it to tell you if the next thing you're going
        to do is going to work.
        """
        url = self.make_url(params)
        return (url in self.connections and
                self.connections[url].is_connected())

    @staticmethod
    def make_url(params):
        """ From device values dictionary, create a url """
        ip = params["ipAddress"]
        port = params["portNumber"]
        return "{0}:{1}".format(ip, port)

    @staticmethod
    def split_url(url):
        port = url.split(":")[-1]
        ip = url[:-(len(port) + 1)]
        return ip, int(port)

    # ----- Logging Configuration ----- #

    def configure_logging(self):
        """ Set up the logging for this module, py4j, and jomnilinkII
        """
        self.configure_logger(log)

        log_py4j = logging.getLogger("py4j")
        self.configure_logger(log_py4j, logging.WARNING, prefix="py4j")

        self.log_omni = logging.getLogger(__name__ + ".jomnilinkII")
        self.configure_logger(self.log_omni)
        self.set_omni_logging_level()

        for name in ["connection", "keychain", "termapp_server"]:
            self.configure_logger(logging.getLogger(name))

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
            self.log_omni.setLevel(logging.DEBUG)
        else:
            self.log_omni.setLevel(logging.ERROR)

    def start_omni_logging(self, stdout, stderr):
        """ Connect the output pipes of our connection subprocess to threads
        that will read lines of output and log them. """
        if stdout is None:
            return
        t = threading.Thread(target=self.read_from_file_write_to_log,
                             name="Omni",
                             args=(self.log_omni, logging.DEBUG, stdout))
        t.setDaemon(True)
        t.start()
        t = threading.Thread(target=self.read_from_file_write_to_log,
                             name="Omni Error",
                             args=(self.log_omni, logging.ERROR, stderr))
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

    hidden = "\u2022" * 15

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
            ip, port = self.split_url(props["url"])
            values["ipAddress"] = ip
            values["portNumber"] = str(port)
            values["prefix"] = props["prefix"]
            enc1, enc2 = self.keychain.get_keys(ip, port)
            values["encryptionKey1"] = enc1
            values["encryptionKey2"] = enc2
        else:
            values["encryptionKey1"] = ""
            values["encryptionKey2"] = ""

        if values["encryptionKey1"]:
            values["hiddenencryptionKey1"] = self.hidden
            values["hiddenencryptionKey2"] = self.hidden

        errors = self.checkConnectionParameters(values)
        if not errors:
            self.make_connection(self.make_url(values),
                                 values["encryptionKey1"],
                                 values["encryptionKey2"])
            if self.did_connection_succeed(values):
                values["isConnected"] = True
        return values, indigo.Dict()

    def validateDeviceFactoryUi(self, values, dev_ids):
        """ Called by the Indigo UI to check values for the Device
        Factory dialog, when the user closes it, and also by the
        callback for the Connect button (see below). This checks the
        syntax of the port number and encryption keys, and
        then tries to connect.

        If a successful connection is made, save the encryption key
        in the keychain and update the pluginProps of all devices
        to match.

        """
        log.debug("Device Factory Config Validation called")

        for key in ["encryptionKey1", "encryptionKey2"]:
            if values["hidden" + key] != self.hidden:
                values[key] = values["hidden" + key]

        errors = self.checkConnectionParameters(values)
        if not errors and not values["isConnected"]:
            self.make_connection(self.make_url(values),
                                 values["encryptionKey1"],
                                 values["encryptionKey2"])
            if self.did_connection_succeed(values):
                self.keychain.save_keys(values["ipAddress"],
                                        values["portNumber"],
                                        values["encryptionKey1"],
                                        values["encryptionKey2"])
                for dev_id in dev_ids:
                    # in case anything changed, make sure all
                    # devices match
                    dev = indigo.devices[dev_id]
                    dev.pluginProps["url"] = self.make_url(values)
                    dev.pluginProps["prefix"] = values["prefix"]
                    dev.replacePluginPropsOnServer(dev.pluginProps)
            else:
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
            if key.startswith("hidden"):
                value = values.get(key[6:], None)
            else:
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

    dialog_value_checks = {
        "portNumber": (is_valid_port_number,
                       "Please enter the controller port number from the "
                       "Setup menu on your Omni system keypad."),
        "hiddenencryptionKey1": (is_valid_encryption_key,
                                 "Please enter the encryption key part 1 from "
                                 "the Setup menu on your Omni system keypad."),
        "hiddenencryptionKey2": (is_valid_encryption_key,
                                 "Please enter the encryption key part 2 from "
                                 "the Setup menu on your Omni system keypad.")}

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
                self.did_connection_succeed(values)):
            url = self.make_url(values)
            for ext in self.extensions:
                results.extend(ext.getDeviceList(url, dev_ids))

        return sorted(results, key=lambda tup: tup[1])

    def createDevices(self, values, dev_ids):
        """ Callback for the Create Devices button in the Device Factory
        dialog. For each selected device type in the deviceGroupList box
        in the dialog, call the appropriate extension and ask it to create
        devices.
        """
        for dev_type in values["deviceGroupList"]:
            ext = self.type_ids_map["device"][dev_type]
            props = {"url": self.make_url(values),
                     "prefix": values["prefix"]}
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
        elif type_id:
            log.debug("No matching plugin extension found for {0} {1} "
                      "method {2}".format(selector, type_id, name))

        if hasattr(indigo.PluginBase, name):
            return getattr(indigo.PluginBase, name)(self, *args)

    # ----- Write info on connected controllers to log (Menu Item)  ----- #

    def writeControllerInfoToLog(self):
        """ Callback for the "Write information on connected OMNI Controllers
        to Log" menu item.
        """
        for c in self.connections.values():
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
                self.say(msg, title=True)
            else:
                self.say_everything_we_know_about(c)

    def say_everything_we_know_about(self, c):
        self.say("HAI/Omni Controller at {0}:{1}".format(c.ip, c.port),
                 title=True)
        reports = ["System Information",
                   "System Troubles",
                   "System Features",
                   "System Capacities",
                   "Zones",
                   "Areas",
                   "Control Units",
                   "Buttons",
                   "Codes",
                   "Thermostats",
                   "Sensors",
                   "Messages",
                   "Audio Zones",
                   "Audio Sources",
                   "Event Log"]

        for report in reports:
            self.say(report + ":", header=True)
            report_func = self.get_report_implementation(report)
            try:
                report_func(report, c, self.say)
            except (Py4JError, ConnectionError):
                pass

    def get_report_implementation(self, report):
        def not_implemented(report, c, say):
            say("Not Implemented")

        for ext in self.extensions:
            if report in ext.reports:
                return ext.reports[report]
        if report in self.standard_queries.keys():
            return self.query_and_print

        return not_implemented

    standard_queries = {
        "Zones": ("OBJ_TYPE_ZONE", "NAMED", "AREA_ALL", "ANY_LOAD"),
        "Areas": ("OBJ_TYPE_AREA", "NAMED_UNNAMED", "NONE", "NONE"),
        "Control Units": ("OBJ_TYPE_UNIT", "NAMED", "AREA_ALL", "ANY_LOAD"),
        "Buttons": ("OBJ_TYPE_BUTTON", "NAMED", "AREA_ALL", "NONE"),
        "Codes": ("OBJ_TYPE_CODE", "NAMED", "AREA_ALL", "NONE"),
        "Thermostats": ("OBJ_TYPE_THERMO", "NAMED", "AREA_ALL", "NONE"),
        "Sensors": ("OBJ_TYPE_AUX_SENSOR", "NAMED", "AREA_ALL", "NONE"),
        "Messages": ("OBJ_TYPE_MESG", "NAMED", "AREA_ALL", "NONE"),
        "Audio Zones": ("OBJ_TYPE_AUDIO_ZONE", "NAMED", "AREA_ALL", "NONE"),
        "Audio Sources": ("OBJ_TYPE_AUDIO_SOURCE", "NAMED", "AREA_ALL", "NONE")
        }

    def query_and_print(self, report, connection, say):
        """ Print whatever jomnilinkII will give us about an object type """
        objname, f1name, f2name, f3name = self.standard_queries[report]

        M = connection.jomnilinkII.Message
        OP = connection.jomnilinkII.MessageTypes.ObjectProperties
        omni = connection.omni

        mtype = M.MESG_TYPE_OBJ_PROP
        objtype = getattr(M, objname)
        filter1 = getattr(OP, "FILTER_1_" + f1name)
        filter2 = getattr(OP, "FILTER_2_" + f2name)
        filter3 = getattr(OP, "FILTER_3_" + f3name)

        objnum = 0
        while True:
            m = omni.reqObjectProperties(objtype, objnum, 1, filter1, filter2,
                                         filter3)
            if m.getMessageType() != mtype:
                break
            self.say(m.toString())
            objnum = m.getNumber()
            try:
                status = omni.reqObjectStatus(objtype, objnum, objnum)
                statuses = status.getStatuses()
                for s in statuses:
                    say(s.toString())
            except (Py4JError, ConnectionError):
                pass

    def say(self, *args, **kwargs):
        header = kwargs.pop("header", False)
        title = kwargs.pop("title", False)
        indent = 0 if title else 4 if header else 8
        indigo.server.log(" " * indent +
                          " ".join([unicode(arg) for arg in args]))

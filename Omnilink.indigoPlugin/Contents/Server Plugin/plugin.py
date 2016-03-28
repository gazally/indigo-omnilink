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
from functools import wraps
import glob
import imp
import logging
import os
import re
import subprocess
import threading
import time

import indigo
import py4j
from py4j.java_gateway import JavaGateway, CallbackServerParameters
from py4j.protocol import Py4JError
from rep_server import start_shell_thread

import extensions
from extensions import ConnectionError

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
        for dev_id, connection in self.connections.items():
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

        # the reason for only adding a handler if there isn't already one
        # is that repeatedly running this code during unit testing
        # ends up adding a handler for each test
        if not logger.handlers:
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
        syntax of the ip address, port number and encryption keys, and
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

    def is_valid_ip(self, ip):
        m = re.match(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$", ip)
        return (m is not None and
                all(map(lambda n: 0 <= int(n) <= 255, m.groups())))

    def is_valid_port_number(self, port):
        return (re.match(r"\d{1,5}", port) is not None and
                0 < int(port) < 65536)

    def is_valid_encryption_key(self, key):
        return re.match(r"^([\dA-F]{2}\-){7}[\dA-F]{2}$", key) is not None

    dialog_keys = ["ipAddress", "portNumber",
                   "encryptionKey1", "encryptionKey2"]

    dialog_value_checks = {
        "ipAddress": (is_valid_ip,
                      "Please enter the controller IP address from the "
                      "Setup menu on your Omni system keypad."),
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
        for k in self.dialog_keys:
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
        namespace = locals().copy()
        namespace.update(globals())
        start_shell_thread("OmniLink Plugin", namespace)


# ----- add methods to the Plugin class to dispatch Indigo calls ----- #

delegator_definitions = [
    ("getActionConfigUiValues", "action",
     "typeId", "", ["self", "pluginProps", "typeId", "actionId"]),

    ("getDeviceConfigUiValues", "device",
     "typeId", "", ["self", "pluginProps", "typeId", "devId"]),

    ("getEventConfigUiValues", "event",
     "typeId", "", ["self", "pluginProps", "typeId", "eventId"]),

    ("validateActionConfigUi", "action",
     "typeId", "", ["self", "valuesDict", "typeId", "actionId"]),

    ("validateEventConfigUi", "event",
     "typeId", "", ["self", "valuesDict", "typeId", "eventId"]),

    ("validateDeviceConfigUi", "device",
     "typeId", "", ["self", "valuesDict", "typeId", "devId"]),

    ("closedActionConfigUi", "action",
     "typeId", "", ["self", "valuesDict", "userCancelled", "typeId",
                    "actionId"]),

    ("closedEventConfigUi", "event",
     "typeId", "", ["self", "valuesDict", "userCancelled", "typeId",
                    "eventId"]),

    ("closedDeviceConfigUi", "device",
     "typeId", "", ["self", "valuesDict", "userCancelled", "typeId", "devId"]),

    ("deviceStartComm", "device", "dev", "deviceTypeId", ["self", "dev"]),

    ("deviceStopComm", "device", "dev", "deviceTypeId", ["self", "dev"]),

    ("deviceCreated", "device", "dev", "deviceTypeId", ["self", "dev"]),

    ("deviceDeleted", "device", "dev", "deviceTypeId", ["self", "dev"]),

    ("deviceUpdated", "device",
     "origDev", "deviceTypeId", ["self", "origDev", "newDev"]),

    ("getDeviceStateList", "device", "dev", "deviceTypeId", ["self", "dev"]),

    ("getDeviceDisplayStateId", "device",
     "dev", "deviceTypeId", ["self", "dev"]),

    ("didDeviceCommPropertyChange", "device",
     "origDev", "deviceTypeId", ["self", "origDev", "newDev"]),

    ("triggerStartProcessing", "event",
     "trigger", "pluginTypeId", ["self", "trigger"]),

    ("triggerStopProcessing", "event",
     "trigger", "pluginTypeId", ["self", "trigger"]),

    ("didTriggerProcessingPropertyChange", "event",
     "origTrigger", "pluginTypeId", ["self", "origTrigger", "newTrigger"]),

    ("triggerCreated", "event",
     "trigger", "pluginTypeId", ["self", "trigger"]),

    ("triggerUpdated", "event",
     "origTrigger", "pluginTypeId", ["self", "origTrigger", "newTrigger"]),

    ("triggerDeleted", "event",
     "trigger", "pluginTypeId", ["self", "trigger"]),
    ]


def make_delegator_func(name, selector, arg_name, arg_attr, argspec):
    """ Rather than have a whole lot of repetitive declarations in the Plugin
    class to dispatch execution of 23 different methods to the appropriate
    plugin extension, build them based on a table.
    arguments:
    name -- name to give new function
    selector -- one of "device", "event" and "action"
    arg_name -- name of argument to constructed function which contains the
                device/event/action type id
    arg_attr -- if the type id is an attribute of the argument arg_name
                this is the name of the attribute
    argspec --  list of arguments to constructed function, to assist in
                locating arg_name by position

    """
    def delegator(self, *args, **kwargs):
        id = (kwargs[arg_name] if arg_name in kwargs
              else args[argspec.index(arg_name) - 1])
        if arg_attr:
            id = getattr(id, arg_attr)
        if id in self.type_ids_map[selector]:
            ext = self.type_ids_map[selector][id]
            if hasattr(ext, name):
                return getattr(ext, name)(*args, **kwargs)
        else:
            log.debug("No matching plugin extension found for {0} {1} "
                      "method {2}".format(selector, id, name))

        return getattr(indigo.PluginBase, name)(self, *args, **kwargs)

    setattr(delegator, "__name__", str(name))
    return delegator

for args in delegator_definitions:
    setattr(Plugin, args[0], make_delegator_func(*args))


class Connection(object):
    """ Maintain the 3 level connection necessary to talk to the Omni II.
    First level: a java process containing the jomnilinkII package and
                 running the Java Gateway Server
    Second level: a JavaGateway object from py4j talking to the java server
    Third level: a Connection object from jomnilinkII talking to the Omni II

    The Connection class owns the first and second levels, and individual
    Connection objects manage the third level.
    """
    javaproc = None
    gateway = None
    java_running = False

    def __init__(self, ip, port, encoding, event_callbacks=[],
                 status_callbacks=[], reconnect_callbacks=[],
                 disconnect_callbacks=[]):
        """
        """
        self.ip, self.port, self.encoding = ip, port, encoding
        self.status_callbacks = status_callbacks
        self.reconnect_callbacks = reconnect_callbacks
        self.event_callbacks = event_callbacks
        self.disconnect_callbacks = disconnect_callbacks
        self._omni = None

        if self.gateway is None:
            return

        self.make_omni_connection()

    def make_omni_connection(self):
        reconnecting = self._omni is not None
        if reconnecting:
            log.debug("Attempting to reconnect to Omni system at " +
                      self.ip)
        else:
            log.debug("Initiating connection with Omni system at " +
                      self.ip)

        self._omni = None
        try:
            jomnilinkII = self.gateway.jvm.com.digitaldan.jomnilinkII
            Message = jomnilinkII.Message

            self._omni = jomnilinkII.Connection(self.ip, self.port,
                                                self.encoding)
            self._omni.setDebug(True)
            self._omni.addNotificationListener(
                NotificationListener(Message, self, self.status_callbacks,
                                     self.event_callbacks))
            self._omni.addDisconnectListener(
                DisconnectListener(self, self.disconnect_callbacks))
            self._omni.enableNotifications()
            log.debug("Successful connection to Omni system at " + self.ip)

        except:
            log.error("Unable to establish connection with Omni system")
            log.debug("Details of Omni Network Communication error: ",
                      exc_info=True)
            log.error("After you correct the problem, please restart the "
                      "Omni Link plugin")
            self._omni = None

        if reconnecting:
            if self.is_connected():
                for c in self.reconnect_callbacks:
                    c(self)

    def is_connected(self):
        return self._omni is not None and self._omni.connected()

    def update(self):
        if self._omni is None:
            return
        if not self._omni.connected():
            self._omni = self.make_omni_connection()

    @property
    def jomnilinkII(self):
        if self.is_connected():
            return self.gateway.jvm.com.digitaldan.jomnilinkII
        else:
            raise ConnectionError

    @property
    def omni(self):
        if self.is_connected():
            return self._omni
        else:
            raise ConnectionError

    @classmethod
    def startup(cls, timeout=5):
        """ Try to launch the java runtime containing jomnilinkII and
        build a py4j gateway to communicate with it. If successful,
        return stdout and stderr pipes from the Java subprocess. If
        not, log an error message and return None,None.
        """
        if cls.javaproc is None:
            try:
                cls._connect_to_java(timeout)
            except (OSError, ConnectionError, Py4JError):
                log.error("Unable to communicate with jomnilinkII library")
                log.debug("", exc_info=True)
                return None, None

        return cls.javaproc.stdout, cls.javaproc.stderr

    @classmethod
    def _connect_to_java(cls, timeout):
        cls.javaproc = subprocess.Popen(
            ["jre/bin/java",
             "-classpath",
             "java/lib/py4j/py4j0.9.1.jar:java/build/jar/OmniForPy.jar",
             "me.gazally.main.MainEntryPoint"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log.debug("Java Runtime started")

        cls._start_output_detection_thread()
        for i in range(timeout * 10):
            time.sleep(0.1)
            if cls.java_running:
                log.debug("Java Gateway Server started")
                break
        else:
            raise ConnectionError("Failed to detect output from Java runtime")
        cls.gateway = JavaGateway(
            start_callback_server=True,
            callback_server_parameters=CallbackServerParameters())

    @classmethod
    def _start_output_detection_thread(cls):
        """ Connect the stdout pipes of our java subprocess to a thread that
        will set self.java_running to True when a line of output is read.
        """
        t = threading.Thread(target=cls._wait_for_output,
                             name="Java Startup")
        t.setDaemon(True)
        t.start()

    @classmethod
    def _wait_for_output(cls):
        """ Wait for a line of text to appear on the output pipe of the
        subprocess. Set self.java_running to True if a line is read or False
        if EOF is encountered first.
        """
        line = cls.javaproc.stdout.readline()  # blocks here if no input
        if line:
            cls.java_running = True

    @classmethod
    def shutdown(cls):
        """ Tidy up """
        try:
            if cls.gateway is not None:
                cls.gateway.shutdown()
            if cls.javaproc is not None:
                cls.javaproc.terminate()
        except:
            log.error("Error shutting down Java gateway")
            log.debug("", exc_info=True)
        cls.gateway = None
        cls.javaproc = None


class NotificationListener(object):
    """ Implementation matching requirements for NotificationListener
    in the jomnilinkII library.
    """
    def __init__(self, Message, connection, status_callbacks, event_callbacks):
        self.messages = {
            Message.OBJ_TYPE_AREA: "STATUS_AREA message",
            Message.OBJ_TYPE_AUDIO_ZONE: "STATUS_AUDIO_ZONE message",
            Message.OBJ_TYPE_AUX_SENSOR: "STATUS_AUX message",
            Message.OBJ_TYPE_EXP: "STATUS_EXP message",
            Message.OBJ_TYPE_MESG: "STATUS_MESG message",
            Message.OBJ_TYPE_THERMO: "STATUS_THERMO message",
            Message.OBJ_TYPE_UNIT: "STATUS_UNIT message",
            Message.OBJ_TYPE_ZONE: "STATUS_ZONE message"
            }
        self.connection = connection
        self.status_callbacks = status_callbacks
        self.event_callbacks = event_callbacks

    def objectStausNotification(self, status):  # it's a jomnilinkII typo
        """ Called back from the jomnilinkII library when a
        Object Status Notification message is received from the Omni
        system. Send the message to all the functions in status_callbacks.
        """
        log.debug(
            self.messages.get(status.getStatusType(),
                              "Unknown type {0}".format(
                                  status.getStatusType())))
        for c in self.status_callbacks:
            c(self.connection, status)

    def otherEventNotification(self, other):
        """ Called back from the jomnilinkII library when an Other
        Event Notification message is received from the Omni system.
        Send the message to all the functions in event_callbacks.
        """
        log.debug("received otherEventNotification")
        for c in self.event_callbacks:
            c(self.connection, other)

    class Java:  # py4j looks for this
        implements = ['com.digitaldan.jomnilinkII.NotificationListener']


class DisconnectListener(object):
    """ Implementation matching requirements for DisconnectListener in
    the jomnilinkII library.
    """
    def __init__(self, connection, callbacks):
        """ Create a DisconnectListener object suitable for registering
        as a callback with a jomnilinkII Connection.
        Arguments:
            connection - a python Connection object (see above)
            callbacks - a list of functions to call when a disconnect
                message is received.
        """
        self.connection = connection
        self.callbacks = callbacks

    def notConnectedEvent(self, e):
        """ Called back from the jomnilinkII library when it detects
        that the Omni system has disconnected. Pass the message on
        to all the callbacks, along with the (python) Connection object
        it came from. """
        log.debug("received notConnectedEvent")
        for c in self.callbacks:
            c(self.connection, e)

    class Java:  # py4j looks for this
        implements = ['com.digitaldan.jomnilinkII.DisconnectListener']

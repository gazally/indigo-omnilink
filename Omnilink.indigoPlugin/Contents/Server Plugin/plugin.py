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
import logging
import re
import subprocess
import threading
import time

import indigo
import py4j
from py4j.java_gateway import JavaGateway, CallbackServerParameters

_VERSION = "0.1.0"
_SLEEP = 0.1

log = logging.getLogger()
log_jomnilinkII = logging.getLogger(__name__ + ".jomnilinkII")

# TODO - Make it possible to change the ports used for Py4J


class Plugin(indigo.PluginBase):
    """Leviton/HAI Omni plugin class for IndigoServer"""

    # ----- plugin framework ----- #

    def __init__(self, plugin_id, display_name, version, prefs):
        indigo.PluginBase.__init__(self, plugin_id, display_name,
                                   version, prefs)
        self.debug = prefs.get("showDebugInfo", False)
        self.debug_jomnilinkII = prefs.get("showJomnilinkIIDebugInfo", False)
        self.configure_logging()

        if (StrictVersion(prefs.get("configVersion", "0.0")) <
                StrictVersion(version)):
            log.debug("Updating config version to " + version)
            prefs["configVersion"] = version

        self.reconnect = False

        self.javaproc = None
        self.java_running = False
        self.gateway = None
        self.omni = None

    def startup(self):
        log.debug("Startup called")
        self.connect_to_java()
        if "ipAddress" in self.pluginPrefs:
            self.reconnect = True
        else:
            log.debug("OmniLink Plugin is not configured")

    def connect_to_java(self):
        try:
            self.javaproc = subprocess.Popen(
                ["java",
                 "-classpath",
                 "java/lib/py4j/py4j0.9.1.jar:java/build/jar/OmniForPy.jar",
                 "me.gazally.main.MainEntryPoint"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError:
            log.error("Unable to start Java subprocess. "
                      "You may need to install the Java JDK from oracle.com "
                      "and then reload this plugin")
            log.debug("", exc_info=True)
            return

        self.start_java_logging()

        for i in range(10):
            time.sleep(0.1)
            if self.java_running:  # this is set by the logging threads
                log.debug("Java Gateway Server started")
                break
        else:
            log.error("Java subprocess did not start or is not communicating")
            return

        try:
            self.gateway = JavaGateway(
                start_callback_server=True,
                callback_server_parameters=CallbackServerParameters())
        except:
            log.error("Unable to create Java communication gateway")
            log.debug("", exc_info=True)

    def shutdown(self):
        log.debug("Shutdown called")
        if self.gateway is not None:
            try:
                self.gateway.shutdown()
            except:
                log.error("Error shutting down Java gateway")
                log.debug("", exc_info=True)
            self.gateway = None

        if self.javaproc is not None:
            self.javaproc.terminate()
            self.javaproc = None

    def update(self):
        if self.gateway is None:
            return
        if self.omni is not None and not self.omni.connected():
            self.reconnect = True
        if self.reconnect:
            log.debug("Initiating connection with Omni system")
            ip = self.pluginPrefs["ipAddress"]
            port = self.pluginPrefs["portNumber"]
            encoding = (self.pluginPrefs["encryptionKey1"] + "-" +
                        self.pluginPrefs["encryptionKey2"])

            try:
                jomnilinkII = self.gateway.jvm.com.digitaldan.jomnilinkII
                Message = jomnilinkII.Message

                self.omni = jomnilinkII.Connection(ip, int(port), encoding)
                self.omni.setDebug(True)
                self.omni.addNotificationListener(NotificationListener(Message))
                self.omni.addDisconnectListener(DisconnectListener())
                self.omni.enableNotifications()

            except py4j.protocol.Py4JJavaError:
                log.error("Unable to establish connection with Omni system. "
                          "Check Omni Link Plugin Configuration")
                log.debug("Details of Omni Network Communication error: ",
                          exc_info=True)
                self.omni = None
                self.reconnect = False  # Don't retry until user changes config

            if self.omni is not None:
                log.debug("Successful connection to Omni system")
                self.reconnect = False

    def runConcurrentThread(self):
        log.debug("Concurrent thread starting")
        try:
            while True:
                self.update()
                self.sleep(_SLEEP)  # seconds
        except self.StopThread:
            log.debug("Concurrent thread stopping")

    # ----- Logging Configuration ----- #

    def configure_logging(self):
        """ Create a Handler subclass for the logging module that uses the
        logging methods supplied to the plugin by Indigo. Prepend the thread
        name to the message if not in the main thread. Use this handler for
        logging in this module as well as py4j and jomnilinkII.
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

        log.addHandler(make_handler(self.debugLog, self.errorLog))
        log.setLevel(logging.DEBUG)

        log_py4j = logging.getLogger("py4j")
        log_py4j.addHandler(make_handler(self.debugLog, self.errorLog,
                                         prefix="py4j"))
        log_py4j.setLevel(logging.WARNING)

        log_jomnilinkII.addHandler(make_handler(self.debugLog, self.errorLog))
        log_jomnilinkII.propagate = False

        self.set_jomnilinkII_logging_level()

    def set_jomnilinkII_logging_level(self):
        """ Set the logging level for logging of the jomnilinkII library """
        if self.debug_jomnilinkII:
            log_jomnilinkII.setLevel(logging.DEBUG)
        else:
            log_jomnilinkII.setLevel(logging.ERROR)

    def start_java_logging(self):
        """ Connect the output pipes of our java subprocess to threads that
        will read lines of output and log them. """
        t = threading.Thread(target=self.read_from_java_write_to_log,
                             name="Comm",
                             args=(log_jomnilinkII,
                                   logging.DEBUG,
                                   self.javaproc.stdout))
        t.setDaemon(True)
        t.start()
        t = threading.Thread(target=self.read_from_java_write_to_log,
                             name="Comm Error",
                             args=(log_jomnilinkII,
                                   logging.ERROR,
                                   self.javaproc.stderr))
        t.setDaemon(True)
        t.start()

    def read_from_java_write_to_log(self, logger, level, pipe):
        """ logging helper function to capture output from subprocess.
        Important side effect: sets self.java_running to True when a line of
        output is read. """
        while True:
            line = pipe.readline()  # blocks here if no input
            if not line:            # EOF
                break
            self.java_running = True
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

        self.debug_jomnilinkII = values.get("showJomnilinkIIDebugInfo", False)
        self.set_jomnilinkII_logging_level()

        parameters = {
            "ipAddress": (self.is_valid_ip,
                          "Please enter the controller IP address from the "
                          "Setup menu on your Omni system keypad."),
            "portNumber": (self.is_valid_port_number,
                           "Please enter the controller port number from the "
                           "Setup menu on your Omni system keypad."),
            "encryptionKey1": (self.is_valid_encryption_key,
                               "Please enter the encryption key part 1 from "
                               "the Setup menu on your Omni system keypad."),
            "encryptionKey2": (self.is_valid_encryption_key,
                               "Please enter the encryption key part 2 from "
                               "the Setup menu on your Omni system keypad."),
            }

        changed = False
        for key, tup in parameters.items():
            is_valid, message = tup
            value = values.get(key, None)
            if value is None or not is_valid(value):
                errors[key] = message
            else:
                old_value = self.pluginPrefs.get(key, None)
                if value != old_value:
                    changed = True

        if errors:
            return (False, values, errors)
        else:
            if changed:
                self.reconnect = True
            return(True, values)

    @staticmethod
    def is_valid_ip(ip):
        m = re.match(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$", ip)
        return (m is not None and
                all(map(lambda n: 0 <= int(n) <= 255, m.groups())))

    @staticmethod
    def is_valid_port_number(port):
        return (re.match(r"\d{1,5}", port) is not None and
                0 < int(port) < 65536)

    @staticmethod
    def is_valid_encryption_key(key):
        return re.match(r"^([\dA-F]{2}\-){7}[\dA-F]{2}$", key) is not None

    # ----- Device Configuration UI ----- #

    def validateDeviceConfigUi(self, values, type_id, device_id):
        """ called by the Indigo UI to validate the values dictionary for
        the Device user interface dialog. Since all the user can do is
        select from lists created by the plugin, don't need to do anything
        here.
        """
        self.debugLog("Device Validation called")
        return (True, values)

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
        if self.debug_jomnilinkII:
            log.debug("Turning off Omni Network Communication debug logging")
        else:
            log.debug("Turning on Omni Network Communication debug logging")
        self.debug_jomnilinkII = not self.debug_jomnilinkII
        self.pluginPrefs["showJomnilinkIIDebugInfo"] = self.debug_jomnilinkII
        self.set_jomnilinkII_logging_level()

    # ----- Device Start and Stop methods  ----- #

    def deviceStartComm(self, device):
        """Called by Indigo Server to tell a device to start working.
        Put the device on the list so RunConcurrentThread will update its
        states.
        """
        props = device.pluginProps
        if "deviceVersion" not in props:
            props["deviceVersion"] = _VERSION
            device.replacePluginPropsOnServer(props)

        log.debug("Starting device {0}".format(device.id))

    def deviceStopComm(self, device):
        """ Called by Indigo Server to tell us it's done with a device.
        """
        log.debug("Stopping device: {0}".format(device.id))


class NotificationListener(object):
    def __init__(self, Message):
        self.messages = {
            Message.OBJ_TYPE_AREA: "STATUS_AREA changed",
            Message.OBJ_TYPE_AUDIO_ZONE: "STATUS_AUDIO_ZONE changed",
            Message.OBJ_TYPE_AUX_SENSOR: "STATUS_AUX changed",
            Message.OBJ_TYPE_EXP: "STATUS_EXP changed",
            Message.OBJ_TYPE_MESG: "STATUS_MESG changed",
            Message.OBJ_TYPE_THERMO: "STATUS_THERMO changed",
            Message.OBJ_TYPE_UNIT: "STATUS_UNIT changed",
            Message.OBJ_TYPE_ZONE: "STATUS_ZONE changed"
            }

    def objectStausNotification(self, status):
        log.debug(
            self.messages.get(status.getStatusType(),
                              "Unknown type {0}".format(
                                  status.getStatusType())))
        statuses = status.getStatuses()
        for s in statuses:
            log.debug(s.toString())

    def otherEventNotification(self, other):  # OtherEventNotifications
        log.debug("otherEventNotification")

    class Java:
        implements = ['com.digitaldan.jomnilinkII.NotificationListener']


class DisconnectListener(object):
    def notConnectedEvent(self, e):
        log.debug("notConnectedEvent")

    class Java:
        implements = ['com.digitaldan.jomnilinkII.DisconnectListener']

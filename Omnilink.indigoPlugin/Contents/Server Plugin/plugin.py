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
import StringIO
import subprocess
import tempfile
import threading
import time

import indigo
from py4j.java_gateway import JavaGateway, CallbackServerParameters

_VERSION = "0.1.0"
_SLEEP = 0.1

log = logging.getLogger()

# TODO - Make it possible to change the ports used for Py4J
# TODO - package py4j with the plugin

class Plugin(indigo.PluginBase):
    """Leviton/HAI Omni plugin class for IndigoServer"""

    # ----- plugin framework ----- #

    def __init__(self, plugin_id, display_name, version, prefs):
        indigo.PluginBase.__init__(self, plugin_id, display_name,
                                   version, prefs)
        self.debug = prefs.get("showDebugInfo", False)
        self.configure_logging()

        if (StrictVersion(prefs.get("configVersion", "0.0")) <
                StrictVersion(version)):
            log.debug("Updating config version to " + version)
            prefs["configVersion"] = version

        self.reconnect = False

        self.gateway = None
        self.java_stdout = None
        self.java_stderr = None

    def startup(self):
        log.debug("Startup called")
        self.connect_to_jvm()
        if "ipAddress" in self.pluginPrefs:
            self.reconnect = True
        else:
            self.errorLog("OmniLink Plugin is not configured")

    def connect_to_jvm(self):
        self.java_stdout = tempfile.NamedTemporaryFile(delete=True)
        self.java_stderr = tempfile.NamedTemporaryFile(delete=True)

        self.javaproc = subprocess.Popen(
            ["/usr/bin/java",
             "-classpath",
             "java/lib/py4j/py4j0.9.1.jar:java/build/jar/OmniForPy.jar",
             "me.gazally.main.MainEntryPoint"],
            stdout=self.java_stdout.file, stderr=self.java_stderr.file)
        time.sleep(0.3) # while loop?
        self.flush_java_logging()
        self.gateway = JavaGateway(start_callback_server=True,
                        callback_server_parameters=CallbackServerParameters())
        self.flush_java_logging()
        
    def shutdown(self):
        log.debug("Shutdown called")
        if self.gateway is not None:
            try:
                self.gateway.shutdown()
            except:
                log.error("Error shutting down Java gateway", exc_info=True)
            finally:
                self.flush_java_logging()
                
        del self.gateway  # force cleanup, otherwise it spits warnings later
        self.gateway = None
        self.javaproc.terminate()
        self.flush_java_logging()
        if self.java_stdout is not None:
            self.java_stdout.close()
        if self.java_stderr is not None:
            self.java_stderr.close()

    def update(self):
        if self.gateway is not None and self.reconnect:
            jomnilinkII = self.gateway.jvm.com.digitaldan.jomnilinkII

            ip = self.pluginPrefs["ipAddress"]
            port = self.pluginPrefs["portNumber"]
            encoding = (self.pluginPrefs["encryptionKey1"] + "-" +
                        self.pluginPrefs["encryptionKey2"])
            self.omni = jomnilinkII.Connection(ip, int(port), encoding)
            self.omni.setDebug(True)
            self.flush_java_logging()

            if self.omni is not None:
                log.debug("got a connection")
                self.reconnect = False

    
    def runConcurrentThread(self):
        log.debug("Concurrent thread starting")
        try:
            while True:
                self.update()
                self.sleep(_SLEEP)  # seconds
        except self.StopThread:
            log.debug("Concurrent Thread Stop")

    # ----- Logging Configuration ----- #

    def configure_logging(self):
        """ Create a Handler subclass for the logging module that uses the
        logging methods supplied to the plugin by Indigo. Prepend the thread
        name to the message if not in the main thread.
        """
        def make_logging_handler(debugLog, errorLog):
            class NewHandler(logging.Handler):
                def emit(self, record):
                    try:
                        msg = self.format(record)
                        threadname = threading.current_thread().name
                        if threadname != "MainThread":
                            msg = ("[Thread] {0}".format(msg))
                        if record.levelno < logging.WARNING:
                            debugLog(msg)
                        else:
                            errorLog(msg)
                    except Exception:
                        self.handleError(record)
            return NewHandler()

        h = make_logging_handler(self.debugLog, self.errorLog)
        log.addHandler(h)
        log.setLevel(logging.DEBUG)

        log_py4j = logging.getLogger("py4j")
        log_py4j.addHandler(h)
        log_py4j.setLevel(logging.WARNING)


    def flush_java_logging(self):
        self.flush_logfile(self.java_stdout, logging.DEBUG)
        self.flush_logfile(self.java_stderr, logging.ERROR)

    def flush_logfile(self, f, level):
        if f.tell() > 0:
            f.seek(0)
            for msg in f.readlines():
                log.log(level, "[Java] " + msg)
            f.seek(0)
        
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
        self.messages = {Message.OBJ_TYPE_AREA: "STATUS_AREA changed",
                         Message.OBJ_TYPE_AUDIO_ZONE: "STATUS_AUDIO_ZONE changed",
			 Message.OBJ_TYPE_AUX_SENSOR: "STATUS_AUX changed",
			 Message.OBJ_TYPE_EXP: "STATUS_EXP changed",
			 Message.OBJ_TYPE_MESG: "STATUS_MESG changed",
			 Message.OBJ_TYPE_THERMO: "STATUS_THERMO changed",
			 Message.OBJ_TYPE_UNIT: "STATUS_UNIT changed",
			 Message.OBJ_TYPE_ZONE: "STATUS_ZONE changed"
                         }

    def objectStausNotification(self, status):
        print(self.messages.get(status.getStatusType(),
                                "Unknown type {0}".format(status.getStatusType())))
        statuses = status.getStatuses()
        for s in statuses:
            print(s.toString())

    def otherEventNotification(self, other): #OtherEventNotifications
        print("otherEventNotification")

    class Java:
        implements = ['com.digitaldan.jomnilinkII.NotificationListener']


class DisconnectListener(object):
    def notConnectedEvent(self, e):
        print("notConnectedEvent")
    class Java:
        implements = ['com.digitaldan.jomnilinkII.DisconnectListener']



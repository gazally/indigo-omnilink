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
import logging
import subprocess
import threading
import time

from py4j.java_gateway import JavaGateway, CallbackServerParameters
from py4j.protocol import Py4JError

log = logging.getLogger(__name__)

"""Connection management for Leviton/HAI Omni plugin for IndigoServer"""


class ConnectionError(RuntimeError):
    """Error raised when the connection to the Omni system is down.
    """
    pass


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

        except Py4JError:
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

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
"""Connection management for Leviton/HAI Omni plugin for IndigoServer"""

import datetime
import logging
import Queue as queue
import subprocess
import threading
import time

from py4j.java_gateway import JavaGateway, CallbackServerParameters
from py4j.protocol import Py4JError, Py4JJavaError

log = logging.getLogger(__name__)

# Seconds until retrying a non-responding address
_TIME_BETWEEN_RETRIES = datetime.timedelta(seconds=60)


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

    Class methods:
    startup(timeout) -- launch the Java subprocess and create the py4j gateway
    shutdown -- close the gateway and kill the subprocess and any instance
                   threads

    Public instance properties:
    omni -- a Connection object from jomnilinkII
    jomnilinkII -- the jomnilinkII Java library

    Public instance methods:
    is_connected -- returns True if the jomnilinkII Connection object exists
                    and claims to be connected
    update -- if the jomnilinkII Connection object says it is no longer
              connected, try to make a new one. This will be done in a separate
              thread so that timeouts from failed network communication don't
              block other work.
    close --  Use when you are done with an instance to tell it to shut down
              a reconnection thread, if it has one.

    """
    javaproc = None
    gateway = None
    java_running = False
    threads = []

    def __init__(self, ip, port, encoding, notifications):
        """ Create a connection to the Omni controller at ip:port using
        the encryption key given by the encoding parameter.
        The notifications parameter should be a dictionary containing
        four lists of functions to call back. The keys are "status",
        "event", "disconnect" and "reconnect", and the first two are used
        to pass along messages coming from the controller and the second
        two to send notifications when the communication link to the controller
        goes down or is brought back up.

        """
        self.ip, self.port, self.encoding = ip, port, encoding
        self.url = "{0}:{1}".format(ip, port)

        self.notification_queue = queue.Queue(maxsize=0)

        self.callbacks = {
            "status":    [self.status_callback] + notifications["status"],
            "event":     [self.event_callback] + notifications["event"],
            "reconnect": ([self.reconnect_callback] +
                          notifications["reconnect"]),
            "disconnect": ([self.disconnect_callback] +
                           notifications["disconnect"])}

        self._omni = None
        self._timestamp = datetime.datetime.now()

        if self.gateway is None or not self.encoding:
            return

        log.debug("Initiating connection with Omni system at {0}".format(
            self.url))
        try:
            self._omni = self._get_omni_link()
        except Py4JError as e:
            log.error("Unable to establish connection with Omni system" +
                      self.message_from_java_error(e))
            log.debug("", exc_info=True)
            self._setup_retry()

    def _setup_retry(self):
        t = threading.Thread(target=self.retry_connection_loop,
                             name="Reconnect")
        t.start()
        self.threads.append(t)

    def retry_connection_loop(self):
        t = threading.currentThread()
        while not getattr(t, "time_to_quit", False):
            time.sleep(1)
            if (datetime.datetime.now() >
                    self._timestamp + _TIME_BETWEEN_RETRIES):
                self._timestamp = datetime.datetime.now()
                log.debug("Attempting to reconnect to Omni system "
                          "at {0}".format(self.url))
                try:
                    omni = self._get_omni_link()
                    self.notification_queue.put(
                        NotificationEvent("reconnect", omni))
                    break
                except Py4JError:
                    log.debug("Attempt failed")
                except:
                    log.debug(exc_info=True)

    @staticmethod
    def message_from_java_error(e):
        """ Try to get a message from a Py4JJavaError. Return the
        message with a ": " tacked on the front, or return the empty
        string if there is no message.
        """
        message = ""
        if isinstance(e, Py4JJavaError):
            try:
                message = ": " + e.args[1].getMessage()
            except (IndexError, Py4JError):
                log.debug("Couldn't decode Py4JJavaError", exc_info=True)
        return message

    def _get_omni_link(self):
        """ Create and set up one of jomnilinkII's connection objects """
        jomnilinkII = self.gateway.jvm.com.digitaldan.jomnilinkII

        omni = jomnilinkII.Connection(self.ip, self.port, self.encoding)
        omni.setDebug(True)

        omni.addNotificationListener(NotificationListener(
            self.notification_queue))
        omni.addDisconnectListener(DisconnectListener(self.notification_queue))
        omni.enableNotifications()

        log.debug("Successful connection to Omni system at " + self.url)
        return omni

    # ----- Callbacks for notification events ----- #

    def status_callback(self, _, status):
        log.debug("Status update message type {0} from {1}".format(
            status.getStatusType(), self.url))

    def event_callback(self, _, other):
        log.debug("Received otherEventNotification from " + self.url)

    def reconnect_callback(self, _, omni):
        log.debug("Sending reconnect notifications")
        self._omni = omni

    def disconnect_callback(self, _, e):
        log.error("Lost communication with {0}: {1}".format(self.url,
                  e.getMessage()))
        self._omni = None
        self._setup_retry()

    # ----- Update connections and process notifications ----- #

    def is_connected(self):
        return self._omni is not None and self._omni.connected()

    def update(self):
        if not self.encoding:
            return

        try:
            while True:
                notify = self.notification_queue.get_nowait()
                for c in self.callbacks[notify.event_type]:
                    c(self, notify.data)
                self.notification_queue.task_done()
        except queue.Empty:
            pass

        if self.is_connected():
            self._timestamp = datetime.datetime.now()

    # ----- Properties to access jomnilinkII and its Connection object ----- #

    @property
    def jomnilinkII(self):
        if self.is_connected():
            return self.gateway.jvm.com.digitaldan.jomnilinkII
        else:
            raise ConnectionError

    @property
    def omni(self):
        if self.is_connected():
            self._timestamp = datetime.datetime.now()
            return self._omni
        else:
            raise ConnectionError

    # ----- Class methods to start up and shut down the java gateway ----- #

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
        subprocess. Set self.java_running to True if a line is read.
        """
        line = cls.javaproc.stdout.readline()  # blocks here if no input
        if line:
            cls.java_running = True

    @classmethod
    def shutdown(cls):
        """ Tidy up """
        for t in cls.threads:
            t.time_to_quit = True
        for t in cls.threads:
            t.join()

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


class NotificationEvent(object):
    def __init__(self, event_type, data):
        self.event_type, self.data = event_type, data


class NotificationListener(object):
    """ Implementation matching requirements for NotificationListener
    in the jomnilinkII library. Puts notifications received on a queue
    so that they can be processed in the main thread.
    """
    def __init__(self, queue):
        self.queue = queue

    def objectStausNotification(self, status):  # it's a jomnilinkII typo
        """ Called back from the jomnilinkII library when a
        Object Status Notification message is received from the Omni
        system.
        """
        self.queue.put(NotificationEvent("status", status))

    def otherEventNotification(self, other):
        """ Called back from the jomnilinkII library when an Other
        Event Notification message is received from the Omni system.
        """
        self.queue.put(NotificationEvent("event", other))

    class Java:  # py4j looks for this
        implements = ['com.digitaldan.jomnilinkII.NotificationListener']


class DisconnectListener(object):
    """ Implementation matching requirements for DisconnectListener in
    the jomnilinkII library. Puts notifications received on a queue
    so that they can be processed in the main thread.
    """
    def __init__(self, queue):
        self.queue = queue

    def notConnectedEvent(self, e):
        """ Called back from the jomnilinkII library when it detects
        that the Omni system has disconnected.
        """
        log.debug("notConnectedEvent")
        self.queue.put(NotificationEvent("disconnect", e))

    class Java:  # py4j looks for this
        implements = ['com.digitaldan.jomnilinkII.DisconnectListener']

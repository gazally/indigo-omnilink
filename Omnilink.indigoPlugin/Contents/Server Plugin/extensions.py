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
""" Plugin Extension Parent Class """
import indigo


class PluginExtensionRegistrar(type):
    """ Metaclass of PluginExtension which keeps track of newly imported
    PluginExtension child classes in a list.
    Public class attribute:
        registry - a list of classes
    Public class method:
        clear - empty the registry list
    """
    registry = []

    def __new__(cls, name, bases, attributes):
        new_cls = type.__new__(cls, name, bases, attributes)
        if new_cls.__module__ != cls.__module__:
            cls.registry.append(new_cls)
        return new_cls

    @classmethod
    def clear(cls):
        cls.registry = []


class PluginExtension(object):
    """Base class for Plugin Extensions.

    Class attributes:
        plugin -- This is set by the plugin instance to itself, so that
            extension methods which get added to the plugin have an easy
            way to access it.
        MODEL -- a string that all extensions should use as the model name
            of new devices they create

    Class attributes which should be changed in the __init__ of subclasses
    to instance attributes:
        type_ids -- This should be set to a dictionary with the keys "device",
            "action" and "event". The values should be strings matching the
            device, action and event type ids defined in the respective xml
            files for the user interface. If two extensions use the same
            type id unpredictable things will happen, so don't do that.
            When the plugin gets a call from indigo to do something
            with a device, action or event it will look up the extension to
            call using the type ids.
        callbacks -- This should be set to a dictionary. Keys should be method
            names (which need to be unique in the plugin namespace) and
            values are functions. These will be added to the plugin dictionary
            so they can be used as user interface callbacks. Please note that
            methods will continue to be bound to the extension so self in
            those callbacks will be the extension instance, not the plugin
            instance. Complaints will be made to the error log if two
            extensions try to add methods with the same name.
        reports -- This should be set to a dictionary. Keys should be selected
            from the following list, and values should be methods with the
            following signature:

            def report_func(report_name, connection, say)

            where connection is a Connection object and say is a method to use
            for output. Report methods should print information from the
            controller in a tidy format, and throw exceptions if they
            encounter communication problems.
            Possible report topics:

                "System Information", "System Troubles", "System Features",
                "System Capacities", "Zones", "Areas", "Units", "Buttons",
                "Codes", "Thermostats", "Sensors", "Messages", "Audio Zones",
                "Audio Sources", "Event Log"

    Methods stubbed in the base class that subclasses may implement:
        getDeviceList
        createDevices
        update
        status_notification
        event_notification
        disconnect_notification
        reconnect_notification

    In addition to the above, when an action/device/trigger with a type id
    found in the type_ids attribute is found in a call to any of the following
    plugin methods, the plugin will examine the extension to see if a method
    of the same name is implemented. If so, it will be called, otherwise
    the plugin will call the method in indigo.PluginBase for the default
    behavior:

        getActionConfigUiValues
        getDeviceConfigUiValues
        getEventConfigUiValues
        validateActionConfigUi
        validateDeviceConfigUi
        validateEventConfigUi
        closedActionConfigUi
        closedDeviceConfigUi
        closedEventConfigUi
        deviceStartComm
        deviceStopComm
        deviceCreated
        deviceDeleted
        deviceUpdated
        getDeviceStateList
        getDeviceDisplayStateId
        didDeviceCommPropertyChange
        actionControlGeneral
        actionControlDimmerRelay
        actionControlSensor
        actionControlSpeedControl
        actionControlThermostat
        actionControlIO
        actionControlSprinkler
        triggerStartProcessing
        triggerStopProcessing
        didTriggerProcessingPropertyChange
        triggerCreated
        triggerUpdated
        triggerDeleted

    """
    # ----- Things that subclasses should not change ----- #
    __metaclass__ = PluginExtensionRegistrar
    plugin = None  # this is set by the calling plugin, to itself
    MODEL = "Omni Link"  # model name for new devices, a constant

    # ----- Things that subclasses should set up in __init__ -----#
    type_ids = None
    callbacks = None
    reports = None

    def getDeviceList(self, props, dev_ids):
        """ this is called when the plugin needs to know what functionality
        is available on the particular Omni system specified by the props
        dictionary. Return a list of tuples, (device type, display string).
        Should catch its own exceptions.
        arguments:
            props -- dictionary containing current settings of device factory
                     dialog
            dev_ids -- list of device_ids in the device factory group
        """
        return []

    def createDevices(self, dev_type, props, prefix, dev_ids):
        """ this is called by the device factory UI code to create devices
        of a type managed by this extension. Implementations should catch
        all exceptions.
        arguments:
            dev_type -- name of device type
            props -- dictionary containing current settings of device factory
                     dialog
            dev_ids -- list of existing device_ids in the device factory group
            prefix -- string prefix to use for creating names
        """
        return props

    def get_unique_name(self, prefix, suffix):
        """Helper function for createDevices. If prefix is not "new device",
        concatenate prefix and suffix and then add digits to that as
        necessary to find a unique name in indigo.devices. Return the
        constructed name, or the empty string.
        """
        name = ""
        if prefix != "new device":
            if prefix and suffix:
                prefix = prefix + " "
            basename = name = prefix + suffix
            count = 0
            while name in indigo.devices:
                count += 1
                name = basename + " " + str(count)
        return name

    def update(self):
        """ This is called on a clock from within RunConcurrentThread.
        Extensions should use this to update devices. """
        pass

    def status_notification(self, connection, status):
        """ Called when the Omni system sends an object status notification.
        This should catch all exceptions.
        arguments:
            connection -- Connection object (from plugin.py, not jomnilinkII)
            status - ObjectStatus object from jomnilinkII
        """
        pass

    def event_notification(self, connection, other):
        """ Called when Omni system sends an "other event" notification.
        Should catch all exceptions.
        arguments:
            connection -- Connection object (from plugin.py, not jomnilinkII)
            other - OtherEventNotifications object from jomnilinkII
        """
        pass

    def disconnect_notification(self, connection, e):
        """ Called when jomnilinkII sends a disconnect notification.
        Should catch all exceptions.
        arguments:
            connection -- Connection object (from plugin.py, not jomnilinkII)
            e -- Java exception
        """
        pass

    def reconnect_notification(self, connection):
        """ Called when the plugin reconnects to the Omni system.
        Should catch all exceptions.
        arguments:
            connection -- Connection object (from plugin.py, not jomnilinkII)
        """
        pass

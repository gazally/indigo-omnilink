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
from collections import defaultdict

import indigo
from py4j.protocol import Py4JError

from connection import ConnectionError

_VERSION = "0.4.0"


class OldVersionError(Exception):
    pass


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

    Notification callbacks that subclasses may implement if they need updates
    as events happen:

    status_notification(self, connection, status):
        Called when the Omni system sends an object status notification.
        This should catch all exceptions.
            connection -- Connection object (from plugin.py, not jomnilinkII)
            status - ObjectStatus object from jomnilinkII

    event_notification(self, connection, status):
        Called when Omni system sends an "other event" notification.
        Should catch all exceptions.
            connection -- Connection object (from plugin.py, not jomnilinkII)
            other - OtherEventNotifications object from jomnilinkII

    disconnect_notification(self, connection, e):
        Called when jomnilinkII sends a disconnect notification.
        Should catch all exceptions.
            connection -- Connection object (from plugin.py, not jomnilinkII)
            e -- Java exception

    reconnect_notification(self, connection, omni):
        Called when the plugin reconnects to the Omni system.
        Should catch all exceptions.
            connection -- existing connections.Connection object
            omni -- new jomnilinkII.Connection object

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

    def getDeviceList(self, url, dev_ids):
        """ this is called when the plugin needs to know what functionality
        is available on the particular Omni system specified by the url.
        Return a list of tuples, (device type, display string).
        Should catch its own exceptions.
        arguments:
            url -- network address of controller
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

    def update(self):
        """ This is called on a clock from within RunConcurrentThread.
        Extensions should use this to update devices. """
        pass


class DeviceMixin(object):
    """ Common functionality shared by all extensions that have devices.
    Meant to be used with PluginExtension (depends on PluginExtension.plugin
    being set).

    Dependency injection is used to get information about the categories of
    devices. The constructor expects to be passed a subclass of Info.

    Public methods:
    info -- Caches Info objects (see __init__), one for each connection
    getDeviceList -- returns list of device type id's this extension manages
    createDevices -- create devices of a given type for the device factory UI
    deviceStartComm -- as in Indigo API. Maintains lists of started devices.
    deviceStopComm -- ditto
    devices_from_url -- iterator for started devices at a given url
    triggerStartProcessing -- as in Indigo API. Maintains lists of started
        triggers.
    triggerStopProcessing -- ditto
    update_device_version -- currently does nothing
    update_device_status -- gets a status object from the Info object
        and updates a device with it
    update_device_from_status -- asks a status object for a list of
        device states to update
    status_notification -- asks the Info object to translate this into
        a status object, gets device states to update and updates device
    disconnect_notification -- sets the disconnected error state
        for affected devices

    Instance attributes:
    device_ids -- dictionary, keys=device type, values=lists of device ids
    triggers -- dictionary, keys=device id, values=lists of trigger ids
    reports -- dictionary, keys=report names, values=a method to print them

    """
    def __init__(self, info_class, logger):
        """ DeviceMixin constructor.
        Arguments:
            info_class -- a subclass of Info
            logger -- a logging.Logger to use
        """

        self.Info = info_class
        self._info = {}
        self.log = logger

        # The key is device type id string, value is list of device id's that
        # are active
        self.device_ids = defaultdict(list)

        # for each device contains a dict
        # which maps event type -> list of triggers
        self.triggers = {}

        self.reports = {}
        for report_name in info_class.reports:
            self.reports[report_name] = self.say_info

    def info(self, url):
        """ Handles caching Info objects by url. Makes a new one if we don't
        have it yet for that url or if the underlying connection object
        has changed. """
        connection = self.plugin.make_connection(url)
        if (url not in self._info or
                self._info[url].connection is not connection):
            self._info[url] = self.Info(connection)
        return self._info[url]

    # ----- Create Devices ----- #

    def getDeviceList(self, url, dev_ids):
        """ Get our Info object for this url and see what device types it has.
        """
        result = []
        try:
            props = self.info(url).props
            result = list(set(((p.device_type, p.type_name) for p in
                               props.values())))
        except (Py4JError, ConnectionError):
            self.log.error("Failed to fetch {0} from the "
                           "Omni Controller".format(self.Info.__name__))
            self.log.debug("", exc_info=True)
        return result

    def createDevices(self, dev_type, values, prefix, dev_ids):
        """Automatically create a device for each item we have properties of,
        unless a device for it already exists.
        """
        old_devs = [indigo.devices[id] for id in dev_ids
                    if indigo.devices[id].deviceTypeId == dev_type]
        values["deviceVersion"] = _VERSION
        try:
            for props in self.info(values["url"]).props.values():
                if props.device_type == dev_type:
                    if not any((dev.pluginProps["number"] == props.number
                                for dev in old_devs)):
                        self.create_device(props, values, prefix)
        except (Py4JError, ConnectionError):
            self.log.error("Failed to fetch {0} from the "
                           "Omni Controller".format(self.Info.__name__))
            self.log.debug("", exc_info=True)

    def create_device(self, props, values, prefix):
        """Create a new device, given properties object and
        values from the Device Factory dialog.
        """
        self.log.debug("Creating device type {2} for {0}:{1}".format(
            props.number, props.name, props.device_type))
        values["number"] = props.number
        kwargs = {"props": values,
                  "deviceTypeId": props.device_type}
        name = self.get_unique_name(prefix, props.name)
        if name:
            kwargs["name"] = name
        newdev = indigo.device.create(indigo.kProtocol.Plugin, **kwargs)
        newdev.model = self.MODEL
        newdev.subModel = props.type_name
        newdev.replaceOnServer()

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

    # ----- Start and stop devices ----- #

    def deviceStartComm(self, device):
        """Start one of the control unit devices. Query the Omni system and
        set the status of the indigo device.
        """
        try:
            self.update_device_version(device)
        except OldVersionError:
            self.log.error('Unfortunately "{0}" was created in a previous '
                           "version of this plugin and cannot be started. "
                           "Please delete and redefine it.".format(
                               device.name))
            device.setErrorStateOnServer("Old version")
            return

        self.log.debug('Starting device "{0}"'.format(device.name))
        if device.id not in self.device_ids[device.deviceTypeId]:
            self.device_ids[device.deviceTypeId].append(device.id)
            self.triggers[device.id] = defaultdict(list)
            self.update_device_status(device)

    def deviceStopComm(self, device):
        if device.id in self.device_ids[device.deviceTypeId]:
            self.log.debug('Stopping device "{0}"'.format(device.name))
            self.device_ids[device.deviceTypeId].remove(device.id)
            del self.triggers[device.id]

    def update_device_version(self, device):
        pass

    def update_device_status(self, dev):
        num = dev.pluginProps["number"]
        try:
            info = self.info(dev.pluginProps["url"])
            props = info.props[num]
            status = info.fetch_status(num)
        except (ConnectionError, Py4JError):
            self.log.debug("Failed to get status of {0} {1} from Omni".format(
                dev.deviceTypeId, num))
            dev.setErrorStateOnServer("disconnected")
            return

        for state, value in props.device_states().items():
            dev.updateStateOnServer(state, value)
        self.update_device_from_status(dev, status)
        dev.setErrorStateOnServer(None)

    def update_device_from_status(self, dev, status):
        for state, value in status.device_states().items():
            dev.updateStateOnServer(state, value)

    def devices_from_url(self, url):
        """ Produce an iteration of device objects matching the given url
        by selecting from self.device_ids """
        for dev_ids_of_type in self.device_ids.values():
            for dev_id in dev_ids_of_type:
                dev = indigo.devices[dev_id]
                if (url == dev.pluginProps["url"]):
                    yield dev

    # ----- Trigger Start and Stop Methods ----- #

    def triggerStartProcessing(self, trigger):
        self.log.debug(
            "Start processing {0} trigger {1}".format(trigger.pluginTypeId,
                                                      str(trigger.id)))
        try:
            dev_id = int(trigger.pluginProps["controllerId"])
            triggers = self.triggers[dev_id][trigger.pluginTypeId]
            if trigger.id not in triggers:
                triggers.append(trigger.id)
        except KeyError:
            self.log.error("Trigger {0} is configured incorrectly".format(
                trigger.id))
            self.log.debug("", exc_info=True)

    def triggerStopProcessing(self, trigger):
        self.log.debug(
            "Stop processing {0} trigger {1}".format(trigger.pluginTypeId,
                                                     trigger.id))
        try:
            dev_id = int(trigger.pluginProps["controllerId"])
            triggers = self.triggers[dev_id][trigger.pluginTypeId]
            triggers.remove(trigger.id)
        except (KeyError, ValueError):
            pass  # deviceStopComm already removed it from the list

    # ----- Callbacks from Omni controller status and events ----- #

    def status_notification(self, connection, status_msg):
        try:
            info = self.info(connection.url)
            number, status = info.number_and_status_from_notification(
                status_msg)
        except (Py4JError, ConnectionError):
            self.log.debug("status_notification exception in {0}".format(
                self.Info.__name__), exc_info=True)
            return

        if status is not None:
            for dev in self.devices_from_url(connection.url):
                if dev.pluginProps["number"] == number:
                    self.update_device_from_status(dev, status)

    def reconnect_notification(self, connection, omni):
        """ Callback used by plugin when successful reconnection
        is made to the Omni controller. Refresh device states.
        """
        for dev in self.devices_from_url(connection.url):
            self.update_device_status(dev)

    def disconnect_notification(self, connection, e):
        """ Callback used by plugin when a disconnect message is
        received from the jomnilinkII library. Put all devices into
        the error state. """
        for dev in self.devices_from_url(connection.url):
            dev.setErrorStateOnServer("not connected")

    def say_info(self, report_name, connection, say):
        self.info(connection.url).report(report_name, say)


class Info(object):
    """ Gathers all info about a class of objects in an Omni controller
    attributes:
        reports -- a list of report names its report method can
                produce
        props -- a dictionary of object properties objects. Key
                 is object number
    public methods:
        report -- print a report on a topic to the log
        fetch_status -- given object number, query Omni for object
                 status and return a Python status object
        number_and_status_from_notification -- given an object
                 status notification, decode it to object number
                 and status object

    utility method for use by subclasses:
        fetch_all_props -- standard loop to iterate through Omni
            controller objects, return a props dictionary

    """
    reports = []

    def fetch_all_props(self, connection, props_class, otype, filter1,
                        filter2, filter3):
        """ Query the connected Omni device for the properties of all the
        named objects matching the object type and filters. Build Properties
        objects out of them, and return a dictionary indexed by object number.
        Raises Py4JJavaError or ConnectionError if there is a
        network error.

        props_class -- constructor for subclass of Props which takes a
            jomnilinkII properties object

        """
        Message = connection.jomnilinkII.Message
        ObjectProps = connection.jomnilinkII.MessageTypes.ObjectProperties
        objnum = 0
        results = {}
        while True:
            m = self.connection.omni.reqObjectProperties(
                getattr(Message, "OBJ_TYPE_" + otype),
                objnum, 1,
                getattr(ObjectProps, "FILTER_1_" + filter1),
                getattr(ObjectProps, "FILTER_2_" + filter2),
                getattr(ObjectProps, "FILTER_3_" + filter3))
            if m.getMessageType() != Message.MESG_TYPE_OBJ_PROP:
                break
            objnum = m.getNumber()
            results[objnum] = props_class(m)
        return results


class Props(object):
    """ Stores configuration information for one object defined
    by an Omni controller.

    required attributes:
        device_type -- an Indigo device type id
        type_name -- display name of device type id
        name -- a name for the device
        number -- number of device used by Omni

    required methods:
        device_states -- return a dictionary of device states to set
            for this object
    """
    pass

class Status(object):
    """ Stores status information for one object defined by an
    Omni controller.

    required methods:
    device_states -- return a dictionary of device states to set
        for the object.
    """
    pass

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
""" Properties and Status Classes, translating jomnilinkII java
objects into something more pythonic
 """


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


class AreaProperties(Props):
    """ AreaProperties class, represents Omni area properties """
    def __init__(self, omni_props):
        """ Construct a AreaProperties object from the jomnilinkII
        Area Properties object.
        """
        self.number = omni_props.getNumber()
        self.name = omni_props.getName()
        if not self.name:
            self.name = "Area {0}".format(self.number)
        self.enabled = omni_props.isEnabled()
        self.exit_delay = omni_props.getExitDelay()
        self.entry_delay = omni_props.getEntryDelay()
        self.device_type = "omniAreaDevice"
        self.type_name = "Area"

    def device_states(self):
        return {"name": self.name,
                "exitDelay": self.exit_delay,
                "entryDelay": self.entry_delay}


class AreaStatus(Status):
    """ AreaStatus class, represents Omni Area status """
    def __init__(self, controller_type, omni_status):
        """ Construct a AreaStatus object from a jomnilinkII
        Area Status object. The controller_type parameter should
        be either "Omni" or "Lumina".
        """
        mode = omni_status.getMode()

        self.mode = self.mode_names[controller_type].get(
            mode & self.mode_delay_mask, "Unknown")
        if mode & self.mode_delay_bit:
            change_delay = "Arming" if controller_type == "Omni" else "Setting"
            self.mode = change_delay + " " + self.mode

        self.alarms = self.decode_alarms(omni_status.getAlarms())
        self.entry_timer = omni_status.getEntryTimer()
        self.exit_timer = omni_status.getExitTimer()

    @classmethod
    def decode_alarms(cls, alarms):
        results = []
        for i, alarm in enumerate(cls.alarm_names):
            if alarms & 1 << i:
                results.append(alarm)
        return results

    def device_states(self):
        results = {"mode": self.mode,
                   "entryTimer": self.entry_timer,
                   "exitTimer": self.exit_timer}
        for alarm in self.alarm_names:
            results["alarm" + alarm] = alarm in self.alarms
        return results

    mode_names = {"Omni": {0: "Off", 1: "Day", 2: "Night",
                           3: "Away", 4: "Vacation", 5: "Day Instant",
                           6: "Night Delayed"},
                  "Lumina": {1: "Home", 2: "Sleep", 3: "Away",
                             4: "Vacation", 5: "Party", 6: "Special"}
                  }
    mode_delay_bit = 0b1000
    mode_delay_mask = 0b0111

    alarm_names = ["Burglary", "Fire", "Gas", "Auxiliary", "Freeze", "Water",
                   "Duress", "Temperature"]


class ControllerProps(Props):
    def __init__(self, connection):
        info = connection.omni.reqSystemInformation()
        self.model, self.base_model, self.sub_model, self.firmware = (
            self._decode_system_info(info))
        self.connection = connection
        self.device_type = "omniControllerDevice"
        self.name = "Controller"
        self.number = 1
        self.type_name = "Controller"

    def _decode_system_info(self, info):
        base_model = self.models.get(info.getModel(), "Unknown")
        sub_model = self.sub_models.get(info.getModel(), "")
        model = "HAI " + base_model + sub_model
        sub_model = sub_model.strip()
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
        return model, base_model, sub_model, firmware

    def device_states(self):
        return {"model": self.model,
                "firmwareVersion": self.firmware}

    models = {30: "Omni",
              16: "Omni",
              36: "Lumina",
              37: "Lumina",
              38: "Omni"}

    sub_models = {30: " IIe",
                  16: "Pro II",
                  36: "",
                  37: " Pro",
                  38: " LTe"}


class ControllerStatus(Status):
    def __init__(self, connection):
        status = connection.omni.reqSystemStatus()
        self.battery_reading = status.getBatteryReading()

        troubles = connection.omni.reqSystemTroubles()
        self.troubles = self._decode_troubles(troubles)

    def _decode_troubles(self, troubles):
        trouble_states = {}
        for t in self.trouble_names:
            trouble_states[t] = False
        for t in troubles.getTroubles():
            trouble_states[self.trouble_names[t - 1]] = True
        return trouble_states

    def device_states(self):
        result = {"batteryReading": self.battery_reading}
        for t, value in self.troubles.items():
            result[t] = value
        return result

    trouble_names = ["freezeTrouble", "batteryLowTrouble", "ACPowerTrouble",
                     "phoneLineTrouble", "digitalCommunicatorTrouble",
                     "fuseTrouble", "freezeTrouble", "batteryLowTrouble"]


class UnitProperties(Props):
    """ UnitProperties class, represents Omni control unit properties """
    def __init__(self, omni_props):
        """ Construct a UnitProperties object from the jomnilinkII
        Unit Properties object.
        """
        self.name = omni_props.getName()
        self.number = omni_props.getNumber()
        unit_type = omni_props.getUnitType()
        self.device_type, self.type_name = \
            self.device_types.get(
                unit_type, ("", "Unknown Unit Type {0}".format(unit_type)))
        self.has_brightness = self.device_type not in self.relay_device_types

    def device_states(self):
        """ Return device states to update based on properties """
        return {"name": self.name}

    device_types = {
        1: ("omniStandardUnit",     "Standard Control"),
        2: ("omniExtendedUnit",     "Extended Control"),
        3: ("omniComposeUnit",      "Compose Control"),
        4: ("omniUPBUnit",          "UPB Control"),
        5: ("omniHLCRoomUnit",      "HLC Room Control"),
        6: ("omniHLCLoadUnit",      "HLC Load Control"),
        7: ("omniLuminaModeUnit",   "Lumina Mode Control"),
        8: ("omniRadioRAUnit",      "Radio RA Control"),
        9: ("omniCentraLiteUnit",   "CentraLite Control"),
        10: ("omniViziaRFRoomUnit", "Vizia RF Room Control"),
        11: ("omniViziaRFLoadUnit", "Vizia RF Load Control"),
        12: ("omniFlagUnit",        "Omni Controller Flag"),
        13: ("omniVoltageUnit",     "Voltage Output Control"),
        14: ("omniAudioZoneUnit",   "Audio Zone Control"),
        15: ("omniAudioSourceUnit", "Audio Source Control"),
    }
    relay_device_types = ["omniFlagUnit", "omniVoltageUnit",
                          "omniAudioZoneUnit", "omniAudioSourceUnit"]


class UnitStatus(Status):
    """ UnitStatus class, represents Omni Unit status """
    def __init__(self, has_brightness, omni_status):
        """ Construct a UnitStatus object from a jomnilinkII
        Unit Status object. """
        self.status = omni_status.getStatus()
        self.time = omni_status.getTime()
        self.has_brightness = has_brightness

    def device_states(self):
        """ Return device states to update based on status """
        result = {"onOffState": self.status != 0,
                  "timeLeftSeconds": self.time}
        if self.has_brightness:
            if self.status == 0:
                result["brightnessLevel"] = 0
            elif 100 <= self.status <= 200:
                result["brightnessLevel"] = self.status - 100
            else:
                # status may store last command sent, meaning we have
                # no way to determine device brighness. But we know it's on.
                result["brightnessLevel"] = 100
        return result


class ZoneProperties(Props):
    """ ZoneProperties class, represents Omni zone properties """
    def __init__(self, omni_props):
        """ Construct a ZoneProperties object from the jomnilinkII
        Zone Properties object.
        """
        self.device_type = "omniZoneDevice"
        self.type_name = "Zone"

        self.name = omni_props.getName()
        self.number = omni_props.getNumber()
        zone_type = omni_props.getZoneType()
        self.zone_type = self.zone_types.get(
            zone_type, "Unknown Zone Type {0}".format(zone_type))
        self.area = omni_props.getArea()

        options = omni_props.getOptions()
        self.cross_zoning = (0b01 & options) != 0
        self.swinger_shutdown = (0b010 & options) != 0
        self.dial_out_delay = (0b0100 & options) != 0

    def device_states(self):
        return {"name": self.name,
                "crossZoning": self.cross_zoning,
                "swingerShutdown": self.swinger_shutdown,
                "dialOutDelay": self.dial_out_delay,
                "type": self.zone_type,
                "area": self.area}

    zone_types = {0: "Entry/Exit",
                  1: "Perimeter",
                  2: "Night Interior",
                  3: "Away Interior",
                  4: "Double Entry Delay",
                  5: "Quadruple Entry Delay",
                  6: "Latching Perimeter",
                  7: "Latching Night Interior",
                  8: "Latching Away Interior",
                  16: "Panic",
                  17: "Police Emergency",
                  18: "Duress",
                  19: "Tamper",
                  20: "Latching Tamper",
                  32: "Fire",
                  33: "Fire Emergency",
                  34: "Gas Alarm",
                  48: "Auxiliary Emergency",
                  49: "Trouble",
                  54: "Freeze",
                  55: "Water",
                  56: "Fire Tamper",
                  64: "Auxiliary",
                  65: "Keyswitch Input",
                  80: "Program Energy Saver Module",
                  81: "Outdoor Temperature",
                  82: "Temperature",
                  83: "Temperature Alarm",
                  84: "Humidity",
                  85: "Extended Range Outdoor Temp",
                  85: "Extended Range Temp",
                  85: "Extended Range Temp Alarm"
                  }


class ZoneStatus(Status):
    """ ZoneStatus class, represents Omni Zone status """
    def __init__(self, omni_status):
        """ Construct a ZoneStatus object from a jomnilinkII
        Zone Status object. """
        status_byte = omni_status.getStatus()
        self.loop = omni_status.getLoop()

        self.condition = self.conditions[status_byte &
                                         self.condition_mask]
        self.latched_alarm = self.latched_alarms[status_byte &
                                                 self.latched_alarm_mask]
        self.arming = self.armings[status_byte &
                                   self.arming_mask]
        self.had_trouble = (status_byte & self.trouble_mask) != 0

    def device_states(self):
        return {"condition": self.condition,
                "onOffState": self.condition == "Secure",
                "alarmStatus": self.latched_alarm,
                "armingStatus": self.arming,
                "hadTrouble": self.had_trouble,
                "sensorValue": self.loop}

    conditions = {0b00: "Secure",
                  0b01: "Not Ready",
                  0b10: "Trouble",
                  0b11: "Undefined"}
    condition_mask = 0b11

    latched_alarms = {0b0000: "Secure",
                      0b0100: "Tripped",
                      0b1000: "Reset",
                      0b1100: "Undefined"}
    latched_alarm_mask = 0b1100

    armings = {0b000000: "Disarmed",
               0b010000: "Armed",
               0b100000: "User Bypass",
               0b110000: "System Bypass"}
    arming_mask = 0b110000

    trouble_mask = 0b1000000

#! /usr/bin/env python
# Unit tests for Indigo Omni Link plugin
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


def build_java_class_mimic(name, argnames, flagnames=[]):
    """ jomnilinkII contains many boilerplate classes that just have a
lot of getWhatever() methods. Build mimics of them, given the list of
Whatevers they contain.

Status_Msg = build_java_class_mimic("Status_Msg",
    ["StatusType", "Statuses"], ["Valid"])

is equivalent to this:

class Status_Msg(object):
    def __init__(self, StatusType, Statuses, Valid):
        self.StatusType, self.Statuses = StatusType, Statuses
        self.Valid = Valid
    def getStatusType(self):
        return self.StatusType
    def getStatuses(self):
        return self.Statuses
    def isValid(self):
        return self.Valid

    def toString(self):
        return " ".join(argnames)

Isn't Python wonderful?
    """
    class Result(object):
        def __init__(self, *args):
            for name, arg in zip(argnames + flagnames, args):
                setattr(self, name, arg)

        def toString(self):
            return " ".join(argnames)

    def make_method(argname):
        def method(self):
            return getattr(self, argname)
        return method

    for name in argnames:
        setattr(Result, "get" + name, make_method(name))
    for name in flagnames:
        setattr(Result, "is" + name, make_method(name))
    Result.__name__ = name
    return Result

SystemInformation = build_java_class_mimic(
    "SystemInformation",
    ["Model", "Major", "Minor", "Revision", "Phone"])

SystemTroubles = build_java_class_mimic("SystemTroubles", ["Troubles"])

SystemStatus = build_java_class_mimic(
    "SystemStatus",
    ["BatteryReading", "Year", "Month", "Day", "Hour", "Minute", "Second",
     "SunriseHour", "SunriseMinute", "SunsetHour", "SunsetMinute", "DayOfWeek",
     "Alarms"], ["TimeDateValid", "DaylightSavings"])

ObjectProperties = build_java_class_mimic(
    "ObjectProperties",
    ["ObjectType", "Number", "Name", "MessageType"])

ZoneProperties = build_java_class_mimic(
    "ZoneProperties",
    ["MessageType", "Name", "Number", "ZoneType", "Area", "Options"])

UnitProperties = build_java_class_mimic(
    "UnitProperties",
    ["MessageType", "Name", "Number", "UnitType"])

EndOfData = build_java_class_mimic("EndOfData", ["MessageType"])

ObjectStatus = build_java_class_mimic(
    "ObjectStatus",
    ["StatusType", "Statuses"])

ZoneStatus = build_java_class_mimic(
    "ZoneStatus",
    ["Number", "Status", "Loop"])

UnitStatus = build_java_class_mimic(
    "UnitStatus",
    ["Number", "Status", "Time"])

SecurityCodeValidation = build_java_class_mimic(
    "SecurityCodeValidation",
    ["CodeNumber", "AuthorityLevel"])

OtherEventNotifications = build_java_class_mimic(
    "OtherEventNotifications",
    ["Notifications"])

EventLogData = build_java_class_mimic(
    "EventLogData",
    ["MessageType", "EventNumber", "Month", "Day", "Hour",
     "Minute", "EventType", "Parameter1", "Parameter2"],
    ["TimeDataValid"])

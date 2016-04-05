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


def build_java_class_mimic(argnames):
    """ jomnilinkII contains many boilerplate classes that just have a
lot of getWhatever() methods. Build mimics of them, given the list of
Whatevers they contain.

Status_Msg = build_java_class_mimic(
    ["StatusType", "Statuses"])

is equivalent to this:

class Status_Msg(object):
    def __init__(self, StatusType, Statuses):
        self.StatusType, self.Statuses = StatusType, Statuses
    def getStatusType(self):
        return self.StatusType
    def getStatuses(self):
        return self.Statuses
    def toString(self):
        return " ".join(argnames)

Isn't Python wonderful?
    """
    class Result(object):
        def __init__(self, *args):
            for name, arg in zip(argnames, args):
                setattr(self, name, arg)

        def toString(self):
            return " ".join(argnames)

    def make_method(argname):
        def method(self):
            return getattr(self, argname)
        return method

    for name in argnames:
        setattr(Result, "get" + name, make_method(name))
    return Result

SystemInformation = build_java_class_mimic(
    ["Model", "Major", "Minor", "Revision", "Phone"])

SystemTroubles = build_java_class_mimic(
    ["Troubles"])

SystemStatus = build_java_class_mimic(
    ["BatteryReading"])

ObjectProperties = build_java_class_mimic(
    ["ObjectType", "Number", "Name", "MessageType"])

ZoneProperties = build_java_class_mimic(
    ["MessageType", "Name", "Number", "ZoneType", "Area", "Options"])

UnitProperties = build_java_class_mimic(
    ["MessageType", "Name", "Number", "UnitType"])

EndOfData = build_java_class_mimic(
    ["MessageType"])

ObjectStatus = build_java_class_mimic(
    ["StatusType", "Statuses"])

ZoneStatus = build_java_class_mimic(
    ["Number", "Status", "Loop"])

UnitStatus = build_java_class_mimic(
    ["Number", "Status", "Time"])

SecurityCodeValidation = build_java_class_mimic(
    ["CodeNumber", "AuthorityLevel"])

OtherEventNotifications = build_java_class_mimic(
    ["Notifications"])

mimic = build_java_class_mimic(
    ["MessageType", "EventNumber", "TimeDataValid", "Month", "Day", "Hour",
     "Minute", "EventType", "Parameter1", "Parameter2"])
mimic.isTimeDataValid = mimic.getTimeDataValid
EventLogData = mimic

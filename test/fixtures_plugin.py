#! /usr/bin/env python
# Unit Tests for Omnilink Plugin for Indigo Server
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
from __future__ import print_function
from __future__ import unicode_literals

import logging
from mock import patch, MagicMock
import os
import sys
from threading import Thread
import time
import xml.etree.ElementTree as ET

from fixtures import (Fixture, CompositeFixture, TestException)
from fixtures_omni import *

import indigo_mock

_VERSION = "0.1.0"

plugin_path = os.path.abspath(
    '../Omnilink.indigoPlugin/Contents/Server Plugin')
if plugin_path not in sys.path:
    sys.path.append(plugin_path)
plugin_module = None


def path_to_xml(fname):
    os.path.join(plugin_path, 'Actions.xml')


xmls = {}

for name in ["Actions", "Devices", "MenuItems", "PluginConfig"]:
    xmls[name] = ET.parse(os.path.join(plugin_path, name + ".xml"))

concurrent_thread_time = 0.1

# ----- Shared Test Fixtures ----- #


class ImportModulesFixture(Fixture):
    def setUp(self, tc):
        # Mock away any modules that should not be in the test environment
        # because they have too many real world side effects
        sys.modules['appscript'] = MagicMock()
        sys.modules['indigo'] = indigo_mock.make_mock_indigo_module(xmls)
        sys.modules['py4j'] = MagicMock()
        sys.modules['py4j.java_gateway'] = sys.modules['py4j'].java_gateway
        sys.modules['py4j.protocol'] = sys.modules['py4j'].protocol

        global plugin_module
        if plugin_module is None:
            # run tests from test directory, or this will fail
            import plugin
            plugin_module = plugin
        else:
            # all of these have global state that affects tests
            reload(logging)
            reload(plugin_module.connection)
            reload(plugin_module)

        tc.plugin_module = plugin_module

        # indigo starts the plugin with current directory set to Server Plugin
        # so do the same here
        os.chdir(plugin_path)
        self.tc = tc

    def tearDown(self):
        # use reset_mock if you are testing an error condition
        self.tc.assertFalse(
            self.tc.plugin_module.indigo.PluginBase.errorLog.called)

PluginEnvironmentFixture = CompositeFixture(ImportModulesFixture,
                                            JomnilinkIIFixture)


class NewPluginFixture(Fixture):
    def setUp(self, tc):
        """ create and start a plugin object """
        props = {}
        props["showDebugInfo"] = False
        props["showJomnilinkIIDebugInfo"] = False

        self.plugin = tc.plugin = tc.plugin_module.Plugin("", "", _VERSION,
                                                          props)

        # patch time.sleep to short circuit the plugin's wait for
        # its java subprocess to start
        sleep = time.sleep
        with patch('connection.time.sleep') as ts:
            ts.side_effect = lambda t: sleep(t/100)
            tc.plugin.startup()

    def tearDown(self):
        self.plugin.shutdown()

    @staticmethod
    def run_concurrent_thread(tc, plugin, time_limit):
        plugin.StopThread = TestException

        class local:
            now = 0

        def sleep(seconds):
            if local.now > time_limit:
                raise TestException("done")
            local.now += seconds

        plugin.sleep = sleep
        t = Thread(target=plugin.runConcurrentThread)
        t.setDaemon(True)
        t.start()
        time.sleep(0.1)
        tc.assertFalse(t.is_alive())

PluginStartedFixture = CompositeFixture(PluginEnvironmentFixture,
                                        NewPluginFixture)

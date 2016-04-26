#! /usr/bin/env python
# Fixtures for testing Indigo OmniLink plugin
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
import sys

from mock import Mock, MagicMock
import pytest

from fixtures.indigo_mockup import *


class Py4JError(Exception):
    pass


class Py4JJavaError(Py4JError):
    pass


@pytest.fixture(scope="session")
def mock_appscript():
    """ Put a mock in sys.modules so that import appscript will work """
    m = Mock()
    sys.modules["appscript"] = m
    return m


@pytest.fixture(autouse=True)
def appscript(plugin_module):
    """ Attach a fresh mock to the plugin in place of appscript """
    plugin_module.appscript = MagicMock()
    return plugin_module.appscript


@pytest.fixture(scope="session")
def mock_py4j():
    """ Put a mock in sys.modules so that import py4j will work """
    m = MagicMock()
    m.protocol.Py4JError = Py4JError
    m.protocol.Py4JJavaError = Py4JJavaError

    sys.modules["py4j"] = m
    sys.modules['py4j.java_gateway'] = sys.modules['py4j'].java_gateway
    sys.modules['py4j.protocol'] = sys.modules['py4j'].protocol
    return m


@pytest.fixture(autouse=True)
def py4j(mock_py4j):
    """ reset and return the mocked up py4j module """
    mock_py4j.reset_mock()
    return mock_py4j


@pytest.fixture(scope="session")
def plugin_module(mock_indigo, mock_appscript, mock_py4j):
    """ Import plugin.py. """
    import plugin
    return plugin


@pytest.fixture(autouse=True)
def logging(plugin_module):
    """ Reload the logging module to clear its internal state """
    # the right way to do this would probably be reload logging
    # but then we'd have to fix up every module in the plugin which has a
    # logger in the module scope. So I decided to hack about in
    # the guts of logging.
    for logger in plugin_module.logging.Logger.manager.loggerDict.values():
        logger.handlers = []
    return plugin_module.logging


@pytest.fixture(autouse=True)
def connection(plugin_module):
    """ reload connection.py to clear its internal state """
    connection = plugin_module.connection
    old_connection_error = plugin_module.connection.ConnectionError
    reload(connection)
    plugin_module.Connection = connection.Connection
    connection.ConnectionError = old_connection_error
    assert connection.Connection.gateway is None
    assert not connection.Connection.threads
    return connection

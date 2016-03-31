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

from unittest import TestCase


class TestException(Exception):
    pass


class Fixture(object):
    """ A simple scheme for test fixtures. Fixtures need to implement
    two methods:
    setUp -- create test setup and put it in attributes of testcase
    tearDown -- do whatever cleanup is necessary
    """
    def setUp(self, testcase):
        pass

    def tearDown(self):
        pass


def CompositeFixture(*fixture_classes):
    """ so you can do this:
    BiggerFixture = CompositeFixture(LittleFixture, OtherLittleFixture)
    A newly created BiggerFixture instance will create instances
    of the fixture classes passed to CompositeFixture. Its setUp method
    will call their setUp methods in order and its tearDown method
    will call their tearDown methods in reverse order.
    """
    class ConstructedFixture(Fixture):
        def __init__(self):
            self._fixtures = [cls() for cls in fixture_classes]

        def setUp(self, testcase):
            [fixture.setUp(testcase) for fixture in self._fixtures]

        def tearDown(self):
            [fixture.tearDown() for fixture in reversed(self._fixtures)]

    ConstructedFixture.__name__ = str("".join((cls.__name__
                                               for cls in fixture_classes)))
    return ConstructedFixture


class TestCaseWithFixtures(TestCase):
    """ Subclass of unittest.TestCase that provides accounting of fixtures.
    Subclasses should call:
    setUp -- do whatever you want, but you need to call
             TestCaseWithFixtures.setUp before using any fixtures
    useFixture -- will create a fixture instance, run its setUp (which
        will build test objects and assign them to the TestCase's
        self.whatever) and add the fixture instance to the list of things
        that need to be torn down
    tearDown -- if a child class implements tearDown,
             TestCaseWithFixtures.tearDown must be called to do cleanup
    """
    def setUp(self):
        self._fixtures = []

    def useFixture(self, cls):
        fixture = cls()
        fixture.setUp(self)
        self._fixtures.append(fixture)
        return fixture

    def tearDown(self):
        [fixture.tearDown() for fixture in reversed(self._fixtures)]

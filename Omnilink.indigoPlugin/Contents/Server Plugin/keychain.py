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
""" Keychain storage of encryption keys for Indigo OmniLink Plugin """

import logging
import subprocess

log = logging.getLogger(__name__)


class KeyChain(object):
    """ Save, Fetch and Cache encryption keys in the OS X Keychain """
    def __init__(self, username):
        self.username = username
        self.cached_encryption_keys = {}

    def get_keys(self, ip, port):
        """ Given an ip address (or hostname), get the
        encryption keys saved in the user's keychain. Return the two parts,
        or two empty strings if it is not there. """

        if (ip, port) in self.cached_encryption_keys:
            return self.cached_encryption_keys[(ip, port)]

        log.debug("Asking keychain for encryption keys for {0}:{1}".format(
            ip, port))
        security = subprocess.Popen(["security", "-i"],
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
        _, result = security.communicate(
            "find-internet-password -a {0} -g -s {1} -P {2}\n".format(
                self.username, ip, port))

        if result.startswith("password: ") and len(result) == 47 + 13:
            log.debug("Found encryption keys in keychain")
            enc_key = result.strip()[11:-1]
            e1, e2 = enc_key[:23], enc_key[24:]
        else:
            log.debug(result)
            log.error("Encryption keys for {0}:{1} not found "
                      "in keychain".format(ip, port))
            e1 = e2 = ""

        self.cached_encryption_keys[(ip, port)] = (e1, e2)
        return e1, e2

    def save_keys(self, ip, port, enc1, enc2):
        """ Given a dictionary with keys ipAddress, portNumber, encryptionKey1
        and encryptionKey2, concatenate the two keys and save them in the
        user's keychain.
        """
        enckey = enc1 + "-" + enc2

        log.debug("Saving encryption keys for {0}:{1} in keychain".format(
            ip, port))
        security = subprocess.Popen(["security", "-i"],
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
        _, result = security.communicate(
            "add-internet-password -a {0} -U -s {1} -P {2} -w {3}\n".format(
                self.username, ip, port, enckey))

        if result != "":
            log.debug(result)
            log.error("Failed to save encryption keys in keychain")

        else:
            self.cached_encryption_keys[(ip, port)] = (enc1, enc2)

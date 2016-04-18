#! /usr/bin/env python
# a little client to run in Terminal.app with readline working
# so a separate process can interact with the user
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

import io
import os
import readline
import sys


def run_client(path):
    """ given a path in which to look for named pipes,
    first write the encoding that sys.stdin is using to
    the uplink pipe (named ".up.fifo"). Then open uplink
    and downlink pipes using that encoding.

    Read lines from the downlink pipe to get commands:
    PROMPT -- get the results of raw_input and write to uplink
    PRINT -- print text not followed by trailing newline
    PRINTLINE -- print text and trailing newline
    """

    encoding = sys.stdin.encoding
    with open(os.path.join(path, ".up.fifo"), "w") as pipeout:
        pipeout.write(encoding + "\n")

    pipein = io.open(os.path.join(path, ".down.fifo"), "r",
                     encoding=encoding, buffering=1)
    pipeout = io.open(os.path.join(path, ".up.fifo"), "w",
                      encoding=encoding, buffering=1)

    def readline():
        while True:
            try:
                return pipein.readline()
            except KeyboardInterrupt:
                print("Sorry, interrupting the interpreter now could "
                      "destabilize the Indigo plugin. If you think it's "
                      "really hung, reloading the plugin from the Indigo "
                      "Plugins menu is probably the best idea.")
    try:
        while True:
            cmd = readline()
            if not cmd:
                break
            elif cmd.startswith("ENCODING"):
                pipeout.write(encoding + "\n")
            elif cmd.startswith("PROMPT "):
                prompt = cmd[7:-1]
                try:
                    line = unicode(raw_input(prompt), encoding)
                except (EOFError, KeyboardInterrupt):
                    break
                pipeout.write(line + "\n")
            elif cmd.startswith("PRINT "):
                print(cmd[6:-1], end="")
            elif cmd.startswith("PRINTLINE "):
                print(cmd[10:-1])
            else:
                print("Client: got unexpected command " + cmd)
                break
    except IOError:
        pass


if __name__ == "__main__":
    run_client(sys.argv[1])

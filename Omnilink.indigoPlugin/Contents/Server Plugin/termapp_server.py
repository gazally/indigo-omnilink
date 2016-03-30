# A little server that interacts with the user via another process inside
# of Terminal.app
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

from __future__ import unicode_literals

import appscript
from code import InteractiveConsole
from contextlib import contextmanager
import logging
import io
import os
from pipes import quote
import shutil
from io import StringIO
import sys
import tempfile
from threading import Thread
from time import sleep

log = logging.getLogger(__name__)


@contextmanager
def redirect_stds(stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr):
    redirected = stdin, stdout, stderr
    original = sys.stdin, sys.stdout, sys.stderr
    sys.stdin, sys.stdout, sys.stderr = redirected
    yield
    sys.stdin, sys.stdout, sys.stderr = original


class Shell(object):
    """Wrapper for the InteractiveConsole push method or other similar
    function. Redirects its output instead of letting it use stdout/stderr.
    """
    def __init__(self, push, inpipe, outpipe):
        self.push_func = push
        self.inpipe, self.outpipe = inpipe, outpipe

    def push(self, line):
        """Feed one line of user input to the interactive object,
        and return a flag indicating which prompt to use next """
        with redirect_stds(stdin=self.inpipe,
                           stdout=self.outpipe, stderr=self.outpipe):
            return self.push_func(line)


class ClientIO(StringIO):
    """ A File Object that translates output into our simple little
    client-server language and sends them through a pipe to the client process.
    The client uses readline to get commands, so they need to end in \n.

    "PROMPT >>> "  asks the client to get a line of input using
                  ">>> " as the prompt.
    "PRINT xyz"  will cause the client to print "xyz", without a newline
    "PRINTLINE xyz"  will cause the to print "xyz" with a trailing newline
    """
    def __init__(self, pipeout):
        self.pipeout = pipeout
        StringIO.__init__(self, "", pipeout.encoding)

    def rm_newlines(self, string):
        return "".join(string.split("\n"))

    def send_prompt(self, prompt):
        self.pipeout.write("PROMPT " + self.rm_newlines(prompt) + "\n")

    def send_line(self, line):
        self.pipeout.write("PRINTLINE " + self.rm_newlines(line) + "\n")

    def send_partial_line(self, line):
        self.pipeout.write("PRINT " + self.rm_newlines(line) + "\n")

    def write(self, string):
        if isinstance(string, str):
            string = unicode(string, self.pipeout.encoding)
        StringIO.write(self, string)
        text = self.getvalue()
        while "\n" in text:
            line, text = text.split("\n")
            self.send_line(line)
        if text:
            self.send_partial_line(text)
        self.seek(0)
        self.truncate()


def run_server(push, prompt, temp_path):
    """Warning in 20 point bold type: this will delete temp_path!!!

    besides that, do a read-eval-print loop doing I/O through named
    pipes set up in the temp_path directory, which will be unlinked
    along with the pipes as soon as they are set up.

    The first thing the client does is write its encoding to the uplink
    pipe. We get that so we can properly open the pipes to handle unicode.
    """
    up = os.path.join(temp_path, ".up.fifo")
    down = os.path.join(temp_path, ".down.fifo")

    if not os.path.exists(up):
        os.mkfifo(up)
    if not os.path.exists(down):
        os.mkfifo(down)

    with open(up, "r", 1) as pipein:
        encoding = pipein.readline()

    p1 = prompt + " >> "
    p2 = prompt + "... "

    try:
        with io.open(down, "w", encoding=encoding, buffering=1) as pipeout:
            with io.open(up, "r", encoding=encoding, buffering=1) as pipein:
                with open(os.devnull, "r") as devnull:
                    shutil.rmtree(temp_path)
                    client = ClientIO(pipeout)
                    shell = Shell(push, devnull, client)

                    more_input = False
                    while True:
                        client.send_prompt(p2 if more_input else p1)
                        line = pipein.readline()
                        if not line:
                            break
                        more_input = shell.push(line[:-1])

    except Exception as e:
        log.debug("Exception in interactive console thread", exc_info=True)


def start_interaction_thread(push, prompt):
    """ Run the python script termapp_client.py (which must be in the current
    directory) in a Terminal window. Set its current directory to the
    current directory, and pass as an argument to it the name of a temporary
    directory where it should look for named pipes to communcate with.

    Arguments:
    push -- a function which takes a line of input and returns True if the
        secondary prompt should be used next and False if the primary prompt
        should be used. push should use sys.stdout and sys.stderr for its
        output, but reading from sys.stdin will just give it EOF.
        prompt is a prefix for the prompt, " >> " will be added to make the
        primary prompt and "... " for the secondary
    """
    path = tempfile.mkdtemp()

    app = appscript.app("Terminal")
    app.do_script("cd {0};python termapp_client.py {1};exit".format(
        quote(os.getcwd()), quote(path)))
    t = Thread(target=run_server, name="console",
               args=(push, prompt, path))
    t.setDaemon(True)
    t.start()
    return t


def start_shell_thread(namespace, prompt):
    return start_interaction_thread(InteractiveConsole(namespace).push, prompt)


if __name__ == "__main__":
    namespace = locals().copy()
    namespace.update(globals())
    t = start_shell_thread(namespace, "[" + __file__ + "]")
    while True:
        if not t.is_alive():
            break
        sleep(1)

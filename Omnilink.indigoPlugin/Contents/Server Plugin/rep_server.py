# Any copyright is dedicated to the Public Domain.
# http://creativecommons.org/publicdomain/zero/1.0/
from __future__ import unicode_literals

import appscript
from code import InteractiveConsole
from contextlib import contextmanager
import os
from pipes import quote
import shutil
import sys
import tempfile
from threading import Thread
from time import sleep


@contextmanager
def change_io(stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr):
    changed = stdin, stdout, stderr
    original = sys.stdin, sys.stdout, sys.stderr
    sys.stdin, sys.stdout, sys.stderr = changed
    yield
    sys.stdin, sys.stdout, sys.stderr = original


def run_server(banner, namespace, temp_path):
    """Warning in 20 point bold type: this will delete temp_path!!!

    besides that, do a read-eval-print loop in the context of
    namespace, doing I/O through two named pipes set up in the
    temp_path directory.
    """

    user_input_name = os.path.join(temp_path, "up.fifo")
    results_name = os.path.join(temp_path, "down.fifo")

    if not os.path.exists(user_input_name):
        os.mkfifo(user_input_name)
    if not os.path.exists(results_name):
        os.mkfifo(results_name)

    shell = InteractiveConsole(namespace)
    try:
        with open(results_name, "w", 0) as pipeout:
            with open(user_input_name, "r", 0) as pipein:
                with change_io(stdin=pipein, stdout=pipeout, stderr=pipeout):
                    shell.interact(banner)
    except:
        pass
    finally:
        shutil.rmtree(temp_path)


def start_shell_thread(banner, namespace):
    """ Run the python script client.py (which must be in the current
    directory) in a Terminal window. Set its current directory to the
    current directory, and pass as an argument to it the name of a temporary
    directory where it should look for named pipes to communcate with. """
    path = tempfile.mkdtemp()
    cwd = os.getcwd()

    app = appscript.app("Terminal")
    app.do_script("cd {0};python rep_client.py {1};exit".format(quote(cwd),
                                                                quote(path)))

    t = Thread(target=run_server, name="console",
               args=(banner, namespace, path))
    t.setDaemon(True)
    t.start()
    return t


if __name__ == "__main__":
    namespace = globals().copy()
    namespace.update(locals())
    t = start_shell_thread("Client-Server Python Intepreter", namespace)
    while True:
        if not t.is_alive():
            break
        sleep(1)

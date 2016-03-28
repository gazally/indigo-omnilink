# Any copyright is dedicated to the Public Domain.
# http://creativecommons.org/publicdomain/zero/1.0/
from __future__ import unicode_literals

import os
import sys
from threading import Thread
from time import sleep

thread_quit = False


def passthrough(inpipe, outpipe):
    try:
        while True:
            ch = inpipe.read(1)
            if not ch:
                break
            outpipe.write(ch)
    finally:
        global thread_quit
        thread_quit = True


def run_client(path):
    pipein = open(os.path.join(path, "down.fifo"), "r", 0)
    pipeout = open(os.path.join(path, "up.fifo"), "w", 0)
    t1 = Thread(target=passthrough, args=(pipein, sys.stdout))
    t2 = Thread(target=passthrough, args=(sys.stdin, pipeout))
    for t in [t1, t2]:
        t.setDaemon(True)
        t.start()

    while True:
        if thread_quit:
            break
        try:
            sleep(0.1)
        except KeyboardInterrupt:
            print ("\nSorry, Keyboard Interrupts can't be passed to the\n"
                   "plugin. If you have hung or crashed the plugin, the best\n"
                   "option is to use Reload from the Indigo Plugins menu.\n")


if __name__ == "__main__":
    run_client(sys.argv[1])

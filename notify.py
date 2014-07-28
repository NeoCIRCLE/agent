#!/usr/bin/env python
# -*- coding: utf-8 -*-

##
# Notify user about vm expiring
##

import cookielib
import errno
import json
import logging
import multiprocessing
import os
import platform
import subprocess
import urllib2

logger = logging.getLogger()
logger.debug("notify imported")
file_name = "vm_renewal.json"
win = platform.system() == "Windows"


def parse_arguments():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--url", type=str, required=True)
    args = parser.parse_args()
    return args


def get_temp_dir():
    if os.getenv("TMPDIR"):
        temp_dir = os.getenv("TMPDIR")
    elif os.getenv("TMP"):
        temp_dir = os.getenv("TMP")
    elif os.path.exists("/tmp"):
        temp_dir = "/tmp"
    elif os.path.exists("/var/tmp"):
        temp_dir = "/var/tmp"
    return temp_dir


def wall(text):
    if win:
        return
    if text is None:
        logger.error("Incorrect function call")
    else:
        process = subprocess.Popen("wall", stdin=subprocess.PIPE, shell=True)
        process.communicate(input=text)[0]


def accept():
    file_path = os.path.join(get_temp_dir(), file_name)
    if not os.path.isfile(file_path):
        print "There is no recent notification to accept."
        return False

    # Load the saved url
    url = json.load(open(file_path, "r"))
    cj = cookielib.CookieJar()
    opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))

    try:
        opener.open(url)  # GET to collect cookies
        cookies = cj._cookies_for_request(urllib2.Request(url))
        token = [c for c in cookies if c.name == "csrftoken"][0].value
        req = urllib2.Request(url, "", {
            "accept": "application/json", "referer": url,
            "x-csrftoken": token})
        rsp = opener.open(req)
        data = json.load(rsp)
        newtime = data["new_suspend_time"]
    except:
        print "Renewal failed. Please try it manually at %s" % url
        logger.exception("renew failed")
        return False
    else:
        print "Renew succeeded. The machine will be suspended at %s." % newtime
        os.remove(file_path)
        return True


def notify(url):
    try:
        logger.debug("notify(%s) called", url)
        if win:
            logger.info("notifying %d clients", len(clients))
            for c in clients:
                logger.debug("sending url %s to client %s", url, unicode(c))
                c.sendLine(url.encode())
        else:
            file_path = os.path.join(get_temp_dir(), file_name)
            if file_already_exists(file_path):
                os.remove(file_path)
                if file_already_exists(file_path):
                    raise Exception(
                        "Couldn't create file %s as new" %
                        file_path)
            with open(file_path, "w") as f:
                json.dump(url, f)
            wall("This virtual machine is going to expire! Please type \n"
                 "  vm_renewal\n"
                 "command to keep it running.")
            logger.debug("wall sent, trying to start browser")
            p = multiprocessing.Process(target=open_in_browser, args=(url, ))
            p.start()
    except:
        logger.exception("Couldn't notify about %s" % url)


def open_in_browser(url):
    if not win:
        display = search_display()
        if display:
            display, uid, gid = display
            os.setgid(gid)
            os.setuid(uid)
            os.environ['DISPLAY'] = display
            logger.debug("DISPLAY=%s", display)
    else:
        display = True

    if display:
        import webbrowser
        webbrowser.open(url, new=2, autoraise=True)


def file_already_exists(name, mode=0o644):
    """Return whether file already exists, create it if not.

    Other errors are silently ignored as the file will be reopened anyways.
    Creating it is needed to avoid race condition.
    """

    try:
        fd = os.open(name, os.O_CREAT | os.O_EXCL, mode)
    except OSError as e:
        if e.errno == errno.EEXIST:
            return True
    else:
        os.close(fd)
    return False


def search_display():
    """Search a valid DISPLAY env var in processes
    """
    env = os.getenv("DISPLAY")
    if env:
        return env

    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        env = os.path.join("/proc", pid, "environ")
        try:
            with open(env, "r") as f:
                envs = dict(line.split("=", 1)
                            for line in f.read().split("\0") if "=" in line)
            if "DISPLAY" in envs and ":" in envs["DISPLAY"]:
                p = os.stat(os.path.join("/proc", pid))
                return envs["DISPLAY"], p.st_uid, p.st_gid
        except:
            continue
    return None

if win:
    from twisted.internet import protocol
    from twisted.protocols import basic

    clients = set()
    port = 25683

    class PubProtocol(basic.LineReceiver):

        def __init__(self, factory):
            self.factory = factory

        def connectionMade(self):
            logger.info("client connected: %s", unicode(self))
            clients.add(self)

        def connectionLost(self, reason):
            logger.info("client disconnected: %s", unicode(self))
            clients.remove(self)

    class PubFactory(protocol.Factory):

        def __init__(self):
            clients.clear()

        def buildProtocol(self, addr):
            return PubProtocol(self)

    def register_publisher(reactor):
        reactor.listenTCP(port, PubFactory(), interface='localhost')

    class SubProtocol(basic.LineReceiver):

        def lineReceived(self, line):
            print "received", line
            open_in_browser(line)

    class SubFactory(protocol.ReconnectingClientFactory):

        def buildProtocol(self, addr):
            return SubProtocol()

    def run_client():
        from twisted.internet import reactor
        print "connect to localhost:%d" % port
        reactor.connectTCP("localhost", port, SubFactory())
        reactor.run()

else:

    def register_publisher(reactor):
        pass


def main():
    args = parse_arguments()
    notify(args.url)

if __name__ == '__main__':
    main()

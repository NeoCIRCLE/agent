#!/usr/bin/env python
# -*- coding: utf-8 -*-

##
# Notify user about vm expiring
##

import json
import logging
import os
import platform
import subprocess
import urllib2
import webbrowser

logger = logging.getLogger()
file_name = "vm_renewal.p"


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
    # Fake data to post so we make urllib2 send a POST instead of a GET
    # do POST request to
    req = urllib2.Request(url, "", {"http_accept": "application/json"})

    try:
        rsp = urllib2.urlopen(req)
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
    if os.getenv("DISPLAY") and platform.system() in ('Linux', 'Windows'):
        webbrowser.open(url, new=2, autoraise=True)
    elif not os.getenv("DISPLAY"):
        if os.path.isfile("%s/%s" % (get_temp_dir(), file_name)):
            logger.info("There is on old request already saved")
        json.dump(url, open("%s/%s" % (get_temp_dir(), file_name), "wb"))
        wall("This virtual machine is going to expire! Please type \n"
             "  vm_renewal\n"
             "command to keep it running.")
    else:
        raise Exception('Not supported system type')


def main():
    args = parse_arguments()
    notify(args.url)

if __name__ == '__main__':
    main()

#!/usr/bin/env python
# -*- coding: utf-8 -*-

##
# Notify user about vm expiring
##

import cookielib
import errno
import json
import logging
import os
import platform
import subprocess
import urllib2
import webbrowser

logger = logging.getLogger()
file_name = "vm_renewal.json"


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
    cj = cookielib.CookieJar()
    opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))

    try:
        opener.open(url)  # GET to collect cookies
        cookies = cj._cookies_for_request(urllib2.Request(url))
        token = [c for c in cookies if c.name == "csrftoken"][0].value
        req = urllib2.Request(url, "", {
            "accept": "application/json", "referer": url,
            "x-csrftoken": token})
            # "content-type": "application/x-www-form-urlencoded"})
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
    olddisplay = os.environ.get("DISPLAY")
    try:
        file_path = os.path.join(get_temp_dir(), file_name)
        if file_already_exists(file_path):
            os.remove(file_path)
            if file_already_exists(file_path):
                raise Exception("Couldn't create file %s as new" % file_path)
        with open(file_path, "w") as f:
            json.dump(url, f)

        if platform.system() != "Windows":
            display = search_display()
            if display:
                os.environ['DISPLAY'] = display

            wall("This virtual machine is going to expire! Please type \n"
                 "  vm_renewal\n"
                 "command to keep it running.")
        else:
            display = True

        if display:
            webbrowser.open(url, new=2, autoraise=True)
    finally:
        if olddisplay:
            os.environ["DISPLAY"] = olddisplay
        elif 'DISPLAY' in os.environ:
            del os.environ["DISPLAY"]



def file_already_exists(name, mode=0644):
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
        except:
            continue
        else:
            if "DISPLAY" in envs and ":" in envs["DISPLAY"]:
                return envs["DISPLAY"]
    return None



def main():
    args = parse_arguments()
    notify(args.url)

if __name__ == '__main__':
    main()

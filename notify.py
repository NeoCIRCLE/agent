#!/usr/bin/env python
# -*- coding: utf-8 -*-

##
# Test program that informs the user about vm incoming time out
##

import platform, logging, os, subprocess, webbrowser, sys
import cPickle as pickle

system = platform.system()
logger = logging.getLogger()
file_name = "vm_renewal.p"

def pars_arguments():
    import argparse
    parser = argparse.ArgumentParser();
    parser.add_argument("-u", "--url", type=str, required=True)
    args = parser.parse_args();
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
    import urllib2
    if not os.path.isfile("%s/%s" % (get_temp_dir(), file_name)):
        logger.error("There isn't a request received currently")
    else:
        done = False
        # Load the saved url
        url = pickle.load(open("%s/%s" % (get_temp_dir(), file_name), "rb"))
        # Fake data to post so we make urllib2 send a POST instead of a GET
        # do POST request to 
        req = urllib2.Request(url, "")
        rsp = urllib2.urlopen(req) 
        
        # Get the result of the request
        success = rsp.info()['renewal']
        if success is not None or rsp.getcode() == 200:
            logger.info("Successfull renew, 200 - OK")
            done = True
        elif rsp.getcode() == 302:
            logger.info("Response is 302 - FOUND")
            done = True
        else:
            logger.error("Renewal failed please try it manually at %s" % url)
        # POST request was sent and received successfully
        if done:
            wall("Successfull renewal of this vm!")
            os.remove("%s/%s" % (get_temp_dir(), file_name))

def notify(url):
    if os.getenv("DISPLAY") and system == 'Linux' or system == 'Windows':
        webbrowser.open(url, new=2, autoraise=True)
    elif not os.getenv("DISPLAY"):
        if os.path.isfile("%s/%s" % (get_temp_dir(), file_name)):
            logger.info("There is on old request already saved")
        pickle.dump(url, open("%s/%s" % (get_temp_dir(), file_name), "wb"))
        wall("This vm is about to time out! Please type vm_renewal command to renew your current process")
    else:
        raise StandardError('Not supported system type')

def main():
    args = pars_arguments()
    notify(args.url)

if __name__ == '__main__':
    main()
#!/usr/bin/python
# -*- coding: utf-8 -*-

##
# Test program that informs the user about vm incoming time out
##

import platform, logging, os, subprocess, webbrowser, sys
if sys.hexversion < 0x03000000 and sys.hexversion > 0x02000000:
    import cPickle as pickle
else:
    import pickle

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
        subprocess.call("echo %s | wall" % text, shell=True)


def accept():
    import httplibs
    if not os.path.isfile("%s/%s" % (get_temp_dir(), file_name)):
        logger.error("There isn't a request received currently")
    else:
        done = False
        # Load the saved url
        url = pickle.load(open("%s/%s" % (get_temp_dir(), file_name), "rb"))
        headers = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain"}
        # Delete https:// or http:// from beginning
        if url[:4].lower() == 'http':
            url = url[url.find("/")+2:]
        # Try to connect to the specified URL
        conn = httplib.HTTPConnection(url[:url.find("/")])
        logger.info("Connection requested to %s" % url[:url.find("/")])
        # Create the POST http request
        conn.request("POST", url[url.find("/"):], "", headers)
        logger.info("Post reques sent to %s" % url)
        # Get the result of the request
        response = conn.getresponse()
        success = response.getheader('renewal')
        if success is None:
            success = ''
        if success.lower() == 'success' or response.status == httplib.OK:
            logger.info("Successfull renew, 200 - OK")
            done = True
        elif response.status == httplib.FOUND:
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
# Open urls in default web browser provided by circle agent
# Part of CIRCLE project http://circlecloud.org/
# Should be in autostart and run by the user logged in

import logging
logger = logging.getLogger()
fh = logging.FileHandler("agent-client.log")
formatter = logging.Formatter(
    "%(asctime)s - %(name)s [%(levelname)s] %(message)s")
fh.setFormatter(formatter)
logger.addHandler(fh)


from notify import run_client

if __name__ == '__main__':
    run_client()

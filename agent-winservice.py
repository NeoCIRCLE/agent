import logging
from logging.handlers import NTEventLogHandler
import os
import servicemanager
import socket
import sys
import win32event
import win32service
import win32serviceutil

from agent import main as agent_main, reactor

logger = logging.getLogger()
fh = NTEventLogHandler(
    "CIRCLE Agent", dllname=os.path.dirname(__file__))
formatter = logging.Formatter(
    "%(asctime)s - %(name)s [%(levelname)s] %(message)s")
fh.setFormatter(formatter)
logger.addHandler(fh)
level = os.environ.get('LOGLEVEL', 'INFO')
logger.setLevel(level)
logger.info("%s loaded", __file__)


class AppServerSvc (win32serviceutil.ServiceFramework):
    _svc_name_ = "circle-agent"
    _svc_display_name_ = "CIRCLE Agent"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        socket.setdefaulttimeout(60)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        reactor.stop()
        logger.info("%s stopped", __file__)

    def SvcDoRun(self):
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                              servicemanager.PYS_SERVICE_STARTED,
                              (self._svc_name_, ''))
        logger.info("%s starting", __file__)
        agent_main()


def main():
    if len(sys.argv) == 1:
        # service must be starting...
        # for the sake of debugging etc, we use win32traceutil to see
        # any unhandled exceptions and print statements.
        import win32traceutil  # noqa
        logger.info("service is starting...")

        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(AppServerSvc)
        # Now ask the service manager to fire things up for us...
        servicemanager.StartServiceCtrlDispatcher()
        logger.info("service done!")
    else:
        win32serviceutil.HandleCommandLine(AppServerSvc)

if __name__ == '__main__':
    try:
        main()
    except (SystemExit, KeyboardInterrupt):
        raise
    except:
        logger.exception("Exception:")

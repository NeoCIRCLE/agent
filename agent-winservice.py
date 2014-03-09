import win32serviceutil
import win32service
import win32event
import servicemanager
import socket

from agent import main as agent_main, reactor


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

    def SvcDoRun(self):
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                              servicemanager.PYS_SERVICE_STARTED,
                              (self._svc_name_, ''))
        agent_main()


if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(AppServerSvc)

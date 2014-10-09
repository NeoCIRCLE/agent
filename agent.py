#!/usr/bin/env python
# -*- coding: utf-8 -*-

from os import environ, chdir
import platform
from shutil import copy
import subprocess
import sys

system = platform.system()

if system == "Linux":
    try:
        chdir(sys.path[0])
        subprocess.call(('pip', 'install', '-r', 'requirements.txt'))
        if system == 'Linux':
            copy("/root/agent/misc/vm_renewal", "/usr/local/bin/")
    except:
        pass  # hope it works


from twisted.internet import reactor, defer
from twisted.internet.task import LoopingCall


import uptime
import logging
from inspect import getargspec, isfunction

from utils import SerialLineReceiverBase

# Note: Import everything because later we need to use the BaseContext
# (relative import error.
from context import BaseContext, get_context, get_serial  # noqa

Context = get_context()

logging.basicConfig()
logger = logging.getLogger()
level = environ.get('LOGLEVEL', 'INFO')
logger.setLevel(level)


class SerialLineReceiver(SerialLineReceiverBase):

    def connectionMade(self):
        self.send_command(
            command='agent_started',
            args={'version': Context.get_agent_version(),
                  'system': system})

        def shutdown():
            self.connectionLost2('shutdown')
            d = defer.Deferred()
            reactor.callLater(0.3, d.callback, "1")
            return d
        reactor.addSystemEventTrigger("before", "shutdown", shutdown)

    def connectionLost2(self, reason):
        self.send_command(command='agent_stopped',
                          args={})

    def tick(self):
        logger.debug("Sending tick")
        try:
            self.send_status()
        except:
            logger.exception("Twisted hide exception")

    def __init__(self):
        super(SerialLineReceiver, self).__init__()
        self.lc = LoopingCall(self.tick)
        self.lc.start(5, now=False)

    def send_status(self):
        import psutil
        disk_usage = {(disk.device.replace('/', '_')):
                      psutil.disk_usage(disk.mountpoint).percent
                      for disk in psutil.disk_partitions()}
        args = {"cpu": dict(psutil.cpu_times()._asdict()),
                "ram": dict(psutil.virtual_memory()._asdict()),
                "swap": dict(psutil.swap_memory()._asdict()),
                "uptime": {"seconds": uptime.uptime()},
                "disk": disk_usage,
                "user": {"count": len(psutil.get_users())}}
        self.send_response(response='status',
                           args=args)

    def _check_args(self, func, args):
        if not isinstance(args, dict):
            raise TypeError("Arguments should be all keyword-arguments in a "
                            "dict for command %s instead of %s." %
                            (self._pretty_fun(func), type(args).__name__))

        # check for unexpected keyword arguments
        argspec = getargspec(func)
        if argspec.keywords is None:  # _operation doesn't take ** args
            unexpected_kwargs = set(args) - set(argspec.args)
            if unexpected_kwargs:
                raise TypeError(
                    "Command %s got unexpected keyword arguments: %s" % (
                        self._pretty_fun(func), ", ".join(unexpected_kwargs)))

        mandatory_args = argspec.args
        if argspec.defaults:  # remove those with default value
            mandatory_args = mandatory_args[0:-len(argspec.defaults)]
        missing_kwargs = set(mandatory_args) - set(args)
        if missing_kwargs:
            raise TypeError("Command %s missing arguments: %s" % (
                self._pretty_fun(func), ", ".join(missing_kwargs)))

    def _get_command(self, command, args):
        if not isinstance(command, basestring) or command.startswith('_'):
            raise AttributeError(u'Invalid command: %s' % command)
        try:
            func = getattr(Context, command)
        except AttributeError as e:
            raise AttributeError(u'Command not found: %s (%s)' % (command, e))

        if not isfunction(func):
            raise AttributeError("Command refers to non-static method %s." %
                                 self._pretty_fun(func))

        self._check_args(func, args)
        return func

    @staticmethod
    def _pretty_fun(fun):
        try:
            argspec = getargspec(fun)
            args = argspec.args
            if argspec.varargs:
                args.append("*" + argspec.varargs)
            if argspec.keywords:
                args.append("**" + argspec.keywords)
            return "%s(%s)" % (fun.__name__, ",".join(args))
        except:
            return "<%s>" % type(fun).__name__

    def handle_command(self, command, args):
        func = self._get_command(command, args)
        retval = func(**args)
        self.send_response(
            response=func.__name__,
            args={'retval': retval, 'uuid': args.get('uuid', None)})

    def handle_response(self, response, args):
        pass


def main():
    # Get proper serial class and port name
    (serial, port) = get_serial()
    logger.info("Opening port %s", port)
    # Open serial connection
    serial(SerialLineReceiver(), port, reactor)
    try:
        from notify import register_publisher
        register_publisher(reactor)
    except:
        logger.exception("Could not register notify publisher")
    logger.debug("Starting reactor.")
    reactor.run()
    logger.debug("Reactor finished.")


if __name__ == '__main__':
    main()

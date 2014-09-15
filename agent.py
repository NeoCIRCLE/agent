#!/usr/bin/env python
# -*- coding: utf-8 -*-

from os import mkdir, environ, chdir
import platform
from shutil import copy
import subprocess
import sys

system = platform.system()

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
import fileinput
import tarfile
from os.path import expanduser, join, exists
from glob import glob
from inspect import getargspec, isfunction
from StringIO import StringIO
from base64 import decodestring
from shutil import rmtree, move
from datetime import datetime

from utils import SerialLineReceiverBase

from ssh import PubKey
from network import change_ip_ubuntu, change_ip_rhel, change_ip_windows


logging.basicConfig()
logger = logging.getLogger()
level = environ.get('LOGLEVEL', 'INFO')
logger.setLevel(level)

SSH_DIR = expanduser('~cloud/.ssh')
AUTHORIZED_KEYS = join(SSH_DIR, 'authorized_keys')

STORE_DIR = '/store'

mount_template_linux = (
    '//%(host)s/%(username)s %(dir)s cifs username=%(username)s'
    ',password=%(password)s,iocharset=utf8,uid=cloud  0  0\n')


distros = {'Scientific Linux': 'rhel',
           'CentOS': 'rhel',
           'CentOS Linux': 'rhel',
           'Debian': 'debian',
           'Ubuntu': 'debian'}
if system == 'Linux':
    distro = distros[platform.linux_distribution()[0]]


# http://stackoverflow.com/questions/12081310/
# python-module-to-change-system-date-and-time
def linux_set_time(time):
    import ctypes
    import ctypes.util

    CLOCK_REALTIME = 0

    class timespec(ctypes.Structure):
        _fields_ = [("tv_sec", ctypes.c_long),
                    ("tv_nsec", ctypes.c_long)]

    librt = ctypes.CDLL(ctypes.util.find_library("rt"))

    ts = timespec()
    ts.tv_sec = int(time)
    ts.tv_nsec = 0

    librt.clock_settime(CLOCK_REALTIME, ctypes.byref(ts))


class Context(object):

    @staticmethod
    def change_password(password):
        if system == 'Linux':
            proc = subprocess.Popen(['/usr/sbin/chpasswd'],
                                    stdin=subprocess.PIPE)
            proc.communicate('cloud:%s\n' % password)
        elif system == 'Windows':
            from win32com import adsi
            ads_obj = adsi.ADsGetObject('WinNT://localhost/%s,user' % 'cloud')
            ads_obj.Getinfo()
            ads_obj.SetPassword(password)

    @staticmethod
    def restart_networking():
        if system == 'Linux':
            if distro == 'debian':
                subprocess.call(['/etc/init.d/networking', 'restart'])
            elif distro == 'rhel':
                subprocess.call(['/bin/systemctl', 'restart', 'network'])
                pass
        elif system == 'Windows':
            pass

    @staticmethod
    def change_ip(interfaces, dns):
        if system == 'Linux':
            if distro == 'debian':
                change_ip_ubuntu(interfaces, dns)
            elif distro == 'rhel':
                change_ip_rhel(interfaces, dns)
        elif system == 'Windows':
            change_ip_windows(interfaces, dns)

    @staticmethod
    def set_time(time):
        if system == 'Linux':
            linux_set_time(float(time))
            try:
                subprocess.call(['/etc/init.d/ntp', 'restart'])
            except:
                pass
        elif system == 'Windows':
            import win32api
            t = datetime.utcfromtimestamp(float(time))
            win32api.SetSystemTime(t.year, t.month, 0, t.day, t.hour,
                                   t.minute, t.second, 0)

    @staticmethod
    def set_hostname(hostname):
        if system == 'Linux':
            if distro == 'debian':
                with open('/etc/hostname', 'w') as f:
                    f.write(hostname)
            elif distro == 'rhel':
                for line in fileinput.input('/etc/sysconfig/network',
                                            inplace=1):
                    if line.startswith('HOSTNAME='):
                        print 'HOSTNAME=%s' % hostname
                    else:
                        print line.rstrip()

            with open('/etc/hosts', 'w') as f:
                f.write("127.0.0.1 localhost\n"
                        "127.0.1.1 %s\n" % hostname)

            subprocess.call(['/bin/hostname', hostname])
        elif system == 'Windows':
            import wmi
            wmi.WMI().Win32_ComputerSystem()[0].Rename(hostname)

    @staticmethod
    def mount_store(host, username, password):
        data = {'host': host, 'username': username, 'password': password}
        if system == 'Linux':
            data['dir'] = STORE_DIR
            if not exists(STORE_DIR):
                mkdir(STORE_DIR)
            # TODO
            for line in fileinput.input('/etc/fstab', inplace=True):
                if not (line.startswith('//') and ' cifs ' in line):
                    print line.rstrip()

            with open('/etc/fstab', 'a') as f:
                f.write(mount_template_linux % data)

            subprocess.call('mount -a', shell=True)

        elif system == 'Windows':
            import notify
            url = 'cifs://%s:%s@%s/%s' % (username, password, host, username)
            for c in notify.clients:
                logger.debug("sending url %s to client %s", url, unicode(c))
                c.sendLine(url.encode())

    @staticmethod
    def get_keys():
        retval = []
        try:
            with open(AUTHORIZED_KEYS, 'r') as f:
                for line in f.readlines():
                    try:
                        retval.append(PubKey.from_str(line))
                    except:
                        logger.exception(u'Invalid ssh key: ')
        except IOError:
            pass
        return retval

    @staticmethod
    def _save_keys(keys):
        print keys
        try:
            mkdir(SSH_DIR)
        except OSError:
            pass
        with open(AUTHORIZED_KEYS, 'w') as f:
            for key in keys:
                f.write(unicode(key) + '\n')

    @staticmethod
    def add_keys(keys):
        if system == 'Linux':
            new_keys = Context.get_keys()
            for key in keys:
                try:
                    p = PubKey.from_str(key)
                    if p not in new_keys:
                        new_keys.append(p)
                except:
                    logger.exception(u'Invalid ssh key: ')
            Context._save_keys(new_keys)

    @staticmethod
    def del_keys(keys):
        if system == 'Linux':
            new_keys = Context.get_keys()
            for key in keys:
                try:
                    p = PubKey.from_str(key)
                    try:
                        new_keys.remove(p)
                    except ValueError:
                        pass
                except:
                    logger.exception(u'Invalid ssh key: ')
            Context._save_keys(new_keys)

    @staticmethod
    def cleanup():
        if system == 'Linux':
            filelist = ([
                '/root/.bash_history'
                '/home/cloud/.bash_history'
                '/root/.ssh'
                '/home/cloud/.ssh']
                + glob('/etc/ssh/ssh_host_*'))
            for f in filelist:
                rmtree(f, ignore_errors=True)

            subprocess.call(('/usr/bin/ssh-keygen', '-A'))

        elif system == 'Windows':
            # TODO
            pass

    @staticmethod
    def start_access_server():
        if system == 'Linux':
            try:
                subprocess.call(('/sbin/start', 'ssh'))
            except OSError:
                subprocess.call(('/bin/systemctl', 'start', 'sshd.service'))

        elif system == 'Windows':
            # TODO
            pass

    @classmethod
    def _update_linux(cls, data, uuid):
        cur_dir = sys.path[0]
        new_dir = cur_dir + '.new'
        old_dir = cur_dir + '.old'
        f = StringIO(decodestring(data))
        try:
            tar = tarfile.TarFile.open("dummy", fileobj=f, mode='r|gz')
            tar.extractall(new_dir)
        except tarfile.ReadError as e:
            logger.error(e)
        else:
            rmtree(old_dir, ignore_errors=True)
            move(cur_dir, old_dir)
            move(new_dir, cur_dir)
            logger.info('Updated')
            reactor.stop()

    @classmethod
    def _update_windows(cls, data, executable, uuid):
        # Extract the tar to the new path
        cur_dir = sys.path[0]
        new_dir = cur_dir + '.version'
        f = StringIO(decodestring(data))
        try:
            tar = tarfile.TarFile.open("dummy", fileobj=f, mode='r|gz')
            tar.extractall(new_dir)
        except tarfile.ReadError as e:
            logger.error(e)
        else:
            cls._update_registry(new_dir, executable)
            logger.info('Updated')
            reactor.stop()

    @classmethod
    def _update_registry(cls, dir, executable):
        # HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\services\circle-agent
        from _winreg import (OpenKeyEx, SetValueEx, QueryValueEx,
                             HKEY_LOCAL_MACHINE, KEY_ALL_ACCESS)
        with OpenKeyEx(HKEY_LOCAL_MACHINE,
                       r'SYSTEM\CurrentControlSet\services\circle-agent',
                       0,
                       KEY_ALL_ACCESS) as key:
            (old_executable, reg_type) = QueryValueEx(key, "ImagePath")
            SetValueEx(key, "ImagePath", None, 2, join(dir, executable))
        return old_executable

    @staticmethod
    def update(data, executable, uuid):
        if system == "Windows":
            Context._update_windows(data, executable, uuid)
        else:
            Context._update_linux(data, executable, uuid)

    @staticmethod
    def ipaddresses():
        import netifaces
        args = {}
        interfaces = netifaces.interfaces()
        for i in interfaces:
            if i == 'lo':
                continue
            args[i] = []
            addresses = netifaces.ifaddresses(i)
            args[i] = ([x['addr']
                        for x in addresses.get(netifaces.AF_INET, [])] +
                       [x['addr']
                        for x in addresses.get(netifaces.AF_INET6, [])
                        if '%' not in x['addr']])
        return args

    @staticmethod
    def get_agent_version():
        try:
            with open('version.txt') as f:
                return f.readline()
        except IOError:
            return None

    @staticmethod
    def send_expiration(url):
        import notify
        notify.notify(url)


class SerialLineReceiver(SerialLineReceiverBase):

    def connectionMade(self):
        self.send_command(
            command='agent_started',
            args={'version': Context.get_agent_version()})

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


def get_virtio_device():
    path = None
    GUID = '{6FDE7521-1B65-48ae-B628-80BE62016026}'
    from infi.devicemanager import DeviceManager
    dm = DeviceManager()
    dm.root.rescan()
    # Search Virtio-Serial by name TODO: search by class_guid
    for i in dm.all_devices:
        if i.has_property("description"):
            if "virtio-serial".upper() in i.description.upper():
                path = ("\\\\?\\" +
                        i.children[0].instance_id.lower().replace('\\', '#') +
                        "#" + GUID.lower()
                        )
    return path


def main():
    if system == 'Windows':
        port = get_virtio_device()
        if port:
            from w32serial import SerialPort
        else:
            from twisted.internet.serial import SerialPort
            import pythoncom
            pythoncom.CoInitialize()
            port = r'\\.\COM1'
    else:
        from twisted.internet.serial import SerialPort
        # Try virtio first
        port = "/dev/virtio-ports/agent"
        if not exists(port):
            port = '/dev/ttyS0'
    logger.info("Opening port %s", port)
    SerialPort(SerialLineReceiver(), port, reactor)
    try:
        from notify import register_publisher
        register_publisher(reactor)
    except:
        logger.exception("Couldnt register notify publisher")
    logger.debug("Starting reactor.")
    reactor.run()
    logger.debug("Reactor after run.")


if __name__ == '__main__':
    main()

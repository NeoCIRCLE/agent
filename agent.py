#!/usr/bin/env python
# -*- coding: utf-8 -*-

from twisted.internet import reactor, defer
from twisted.internet.task import LoopingCall
from twisted.internet.serialport import SerialPort

import uptime
import logging
import subprocess
import fileinput
import platform
import sys
import tarfile
from os.path import expanduser, join, exists
from os import mkdir, environ
from glob import glob
from inspect import getargspec
from StringIO import StringIO
from base64 import decodestring
from shutil import rmtree, move
from datetime import datetime
from types import FunctionType

from utils import SerialLineReceiverBase

from ssh import PubKey


logging.basicConfig()
logger = logging.getLogger()
level = environ.get('LOGLEVEL', 'INFO')
logger.setLevel(level)


SSH_DIR = expanduser('~cloud/.ssh')
AUTHORIZED_KEYS = join(SSH_DIR, 'authorized_keys')

STORE_DIR = '/store'

mount_template_linux = (
    '//%(host)s/u-1 %(dir)s cifs username=%(username)s'
    ',password=%(password)s,iocharset=utf8,uid=cloud  0  0\n')

mount_template_windows = (
    'net use * /delete /yes\r\n'
    'timeout 5\r\n'
    'net use z: \\%(host)s\\%(username)s "%(password)s" '
    '/user:%(username)s\r\n')


system = platform.system()
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
                with open('/etc/network/interfaces', 'w') as f:
                    f.write('auto lo\n'
                            'iface lo inet loopback\n'
                            'auto eth0\n'
                            'iface eth0 inet dhcp\n')
                subprocess.call(['/etc/init.d/networking', 'restart'])
            elif distro == 'rhel':
                with open('/etc/sysconfig/network-scripts/ifcfg-eth0',
                          'w') as f:
                    f.write('DEVICE=eth0\n'
                            'BOOTPROTO=dhcp\n'
                            'ONBOOT=yes\n')

        elif system == 'Windows':
            import wmi
            w = wmi.WMI()
            nic = w.Win32_NetworkAdapterConfiguration(IPEnabled=True)[0]
            assert nic.EnableDHCP()[0] == 0

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
            with open(r'c:\Windows\System32\Repl\Import\Scripts\%s.bat'
                      % username, 'w') as f:
                f.write(mount_template_windows % data)

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

    @staticmethod
    def update(data, uuid):
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
        self.send_status()

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

    def _get_command(self, command, args):
        if not isinstance(command, basestring) or command.startswith('_'):
            raise AttributeError(u'Invalid command: %s' % command)
        try:
            func = getattr(Context, command)
        except AttributeError as e:
            raise AttributeError(u'Command not found: %s (%s)' % (command, e))

        if not isinstance(func, FunctionType):
            raise AttributeError("Command refers to non-static method %s." %
                                 unicode(func))

        # check for unexpected keyword arguments
        argspec = getargspec(func)
        if argspec.keywords is None:  # _operation doesn't take ** args
            unexpected_kwargs = set(args) - set(argspec.args)
            if unexpected_kwargs:
                raise TypeError("Command got unexpected keyword arguments: "
                                "%s" % ", ".join(unexpected_kwargs))

            if argspec.defaults:
                mandatory_args = argspec.args[0:-len(argspec.defaults)]
            else:
                mandatory_args = argspec.args
            missing_kwargs = set(mandatory_args) - set(args)
            if missing_kwargs:
                raise TypeError("Command %s missing arguments: %s" % (
                    unicode(func), ", ".join(missing_kwargs)))

        return func

    def handle_command(self, command, args):
        func = self._get_command(command, args)
        retval = func(**args)
        self.send_response(
            response=func.__name__,
            args={'retval': retval, 'uuid': args.get('uuid', None)})

    def handle_response(self, response, args):
        pass


def main():
    if system == 'Windows':
        import pythoncom
        pythoncom.CoInitialize()
        port = r'\\.\COM1'
    else:
        port = '/dev/ttyS0'
    SerialPort(SerialLineReceiver(), port, reactor, baudrate=115200)
    try:
        from notify import register_publisher
        register_publisher(reactor)
    except:
        logger.exception("Couldnt register notify publisher")
    reactor.run()


if __name__ == '__main__':
    main()

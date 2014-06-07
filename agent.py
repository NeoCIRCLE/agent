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
from glob import glob
from StringIO import StringIO
from base64 import decodestring
from shutil import rmtree, move
from datetime import datetime

from utils import SerialLineReceiverBase

logger = logging.getLogger()

fstab_template = ('sshfs#%(username)s@%(host)s:home /home/cloud/sshfs '
                  'fuse defaults,idmap=user,reconnect,_netdev,uid=1000,'
                  'gid=1000,allow_other,StrictHostKeyChecking=no,'
                  'IdentityFile=/home/cloud/.ssh/id_rsa 0 0\n')


system = platform.system()
distros = {'Scientific Linux': 'rhel',
           'CentOS': 'rhel',
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
                f.write('127.0.0.1 localhost'
                        '127.0.1.1 %s\n' % hostname)

            subprocess.call(['/bin/hostname', hostname])
        elif system == 'Windows':
            import wmi
            wmi.WMI().Win32_ComputerSystem()[0].Rename(hostname)

    @staticmethod
    def mount_store(host, username, password, key):
        if system == 'Linux':
            for line in fileinput.input('/etc/fstab', inplace=1):
                if line.startswith('sshfs#'):
                    line = ''

            with open('/etc/fstab', 'a') as f:
                f.write(fstab_template % {'host': host, 'username': username,
                                          'password': password})

        elif system == 'Windows':
            data = ('net use * /delete /yes\r\n'
                    'timeout 5\r\n'
                    'net use z: \\%(hostname)s\\%(username)s "%(password)s" '
                    '/user:%(username)s')
            with open(r'c:\Windows\System32\Repl\Import\Scripts'
                      r'%s.bat' % username, 'w') as f:
                f.write(data)

    @staticmethod
    def cleanup():
        if system == 'Linux':
            filelist = ((
                '/root/.bash_history'
                '/home/cloud/.bash_history'
                '/root/.ssh'
                '/home/cloud/.ssh')
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
            subprocess.call(('/sbin/start', 'ssh'))

        elif system == 'Windows':
            # TODO
            pass

    @staticmethod
    def update(data):
        cur_dir = sys.path[0]
        new_dir = cur_dir + '.new'
        old_dir = cur_dir + '.old'
        f = StringIO(decodestring(data))
        try:
            tar = tarfile.TarFile.open("dummy", fileobj=f, mode='r|bz2')
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


class SerialLineReceiver(SerialLineReceiverBase):
    def connectionMade(self):
        self.send_command(command='agent_started',
                          args={})

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
        import psutil  # TODO ez azért kell itt van importálva, mert
                       # windows alatt kilépéskor kressel tőle a python
                       # így a service azt hiszi, hogy nem indult el rendesen
        disk_usage = {(disk.device.replace('/', '_')):
                      psutil.disk_usage(disk.mountpoint).percent
                      for disk in psutil.disk_partitions()}
        args = {"cpu": dict(psutil.cpu_times().__dict__),
                "ram": dict(psutil.virtual_memory().__dict__),
                "swap": dict(psutil.swap_memory().__dict__),
                "uptime": {"seconds": uptime.uptime()},
                "disk": disk_usage,
                "user": {"count": len(psutil.get_users())}}
        self.send_response(response='status',
                           args=args)

    def handle_command(self, command, args):
        if not isinstance(command, basestring) or command.startswith('_'):
            raise Exception(u'Invalid command: %s' % command)

        for k, v in args.iteritems():
            if not (isinstance(v, int) or isinstance(v, float) or
                    isinstance(v, basestring)):
                raise Exception(u'Invalid argument: %s' % k)

        try:
            func = getattr(Context, command)
            retval = func(**args)
        except (AttributeError, TypeError) as e:
            raise Exception(u'Command not found: %s (%s)' % (command, e))
        else:
            if retval:
                self.send_response(response=func.__name__, args=retval)

    def handle_response(self, response, args):
        pass


def main():
    if system == 'Windows':
        port = r'\\.\COM1'
    else:
        port = '/dev/ttyS0'
    SerialPort(SerialLineReceiver(), port, reactor, baudrate=115200)

    reactor.run()

if __name__ == '__main__':
    main()

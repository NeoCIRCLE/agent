#!/usr/bin/env python

from twisted.internet import reactor, defer
from twisted.internet.task import LoopingCall
from twisted.internet.serialport import SerialPort

import psutil
import uptime
import subprocess
#import netifaces
import platform
from datetime import datetime

from utils import SerialLineReceiverBase


class Context(object):
    @staticmethod
    def change_password(new_password):
        system = platform.system()
        if system == 'Linux':
            proc = subprocess.Popen(['/usr/bin/sudo',
                                     '/usr/sbin/chpasswd'],
                                    stdin=subprocess.PIPE)
            proc.communicate('cloud:%s\n' % new_password)
        elif system == 'Windows':
            from win32com import adsi
            ads_obj = adsi.ADsGetObject('WinNT://localhost/%s,user' % 'cloud')
            ads_obj.Getinfo()
            ads_obj.SetPassword(new_password)

    @staticmethod
    def restart_networking():
        system = platform.system()
        if system == 'Linux':
            interfaces = '''
                auto lo
                iface lo inet loopback
                auto eth0
                iface eth0 inet dhcp
            '''
            proc = subprocess.Popen(['/usr/bin/sudo', '/usr/bin/tee',
                                     '/etc/network/interfaces'],
                                    stdin=subprocess.PIPE)
            proc.communicate(interfaces)
            subprocess.call(['/usr/bin/sudo', '/etc/init.d/networking',
                             'restart'])
        elif system == 'Windows':
            import wmi
            w = wmi.WMI()
            nic = w.Win32_NetworkAdapterConfiguration(IPEnabled=True)[0]
            assert nic.EnableDHCP()[0] == 0

    @staticmethod
    def set_time(new_time):
        system = platform.system()
        if system == 'Linux':
            subprocess.call(['/usr/bin/sudo',
                             '/etc/init.d/openntpd', 'restart'])
        elif system == 'Windows':
            import win32api
            t = datetime.utcfromtimestamp(float(new_time))
            win32api.SetSystemTime(t.year, t.month, 0, t.day, t.hour,
                                   t.minute, t.second, 0)

    @staticmethod
    def set_hostname(new_hostname):
        system = platform.system()
        if system == 'Linux':
            # /etc/hostname
            proc = subprocess.Popen(['/usr/bin/sudo', '/usr/bin/tee',
                                     '/etc/hostname'],
                                    stdin=subprocess.PIPE)
            proc.communicate(new_hostname)
            # /etc/hosts
            proc = subprocess.Popen(['/usr/bin/sudo', '/usr/bin/tee', '-a',
                                     '/etc/hosts'],
                                    stdin=subprocess.PIPE)
            proc.communicate('127.0.1.1 %s\n' % new_hostname)
            subprocess.call(['/usr/bin/sudo', '/bin/hostname',
                             new_hostname])
        elif system == 'Windows':
            import wmi
            wmi.WMI().Win32_ComputerSystem()[0].Rename(new_hostname)

    @staticmethod
    def mount_store(host, username, password, key):
        system = platform.system()
        if system == 'Linux':
            data = ('sshfs#%(username)s@%(host)s:home /home/cloud/sshfs '
                    'fuse defaults,idmap=user,reconnect,_netdev,uid=1000,'
                    'gid=1000,allow_other,StrictHostKeyChecking=no,'
                    'IdentityFile=/home/cloud/.ssh/id_rsa 0 0\n')
            proc = subprocess.Popen(['/usr/bin/sudo', '/usr/bin/tee', '-a',
                                     '/etc/fstab'],
                                    stdin=subprocess.PIPE)
            proc.communicate(data % {'host': host,
                                     'username': username,
                                     'password': password})

        elif system == 'Windows':
            data = ('net use * /delete /yes\r\n'
                    'timeout 5\r\n'
                    'net use z: \\%(hostname)s\\%(username)s "%(password)s" '
                    '/user:%(username)s')
            with open(r'c:\Windows\System32\Repl\Import\Scripts'
                      r'%s.bat' % username, 'w') as f:
                f.write(data)


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

    def send_ipaddresses(self):
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
        self.send_response(response='ipaddresses',
                           args=args)

    def handle_command(self, command, args):
        if command == 'ping':
            self.send_response(response='pong',
                               args=args)
        elif command == 'status':
            self.send_status()
        elif command == 'get_ipaddresses':
            self.send_ipaddresses()
        elif command == 'change_password':
            Context.change_password(str(args['password']))
        elif command == 'restart_networking':
            Context.restart_networking()
        elif command == 'set_time':
            Context.set_time(str(args['time']))
        elif command == 'set_hostname':
            Context.set_hostname(str(args['hostname']))
        elif command == 'mount_store':
            Context.mount_store(str(args['host']),
                                str(args['username']),
                                str(args['password']),
                                str(args['key']))

    def handle_response(self, response, args):
        pass


def main():
    system = platform.system()
    if system == 'Windows':
        port = r'\\.\COM1'
    else:
        port = '/dev/ttyS0'
    SerialPort(SerialLineReceiver(), port, reactor, baudrate=115200)

    reactor.run()

if __name__ == '__main__':
    main()

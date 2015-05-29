#!/usr/bin/env python
# -*- coding: utf-8 -*-

from os import mkdir
import platform
from shutil import rmtree, move
import subprocess
import sys

working_directory = sys.path[0]

import logging
import fileinput
import tarfile
from os.path import expanduser, join, exists
from glob import glob
from StringIO import StringIO
from base64 import decodestring
from hashlib import md5


from ssh import PubKey
from .network import change_ip_ubuntu, change_ip_rhel
from context import BaseContext

from twisted.internet import reactor

logger = logging.getLogger()

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
distro = distros[platform.linux_distribution()[0]]


class Context(BaseContext):

    # http://stackoverflow.com/questions/12081310/
    # python-module-to-change-system-date-and-time
    def _linux_set_time(time):
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

    @staticmethod
    def change_password(password):
        proc = subprocess.Popen(['/usr/sbin/chpasswd'],
                                stdin=subprocess.PIPE)
        proc.communicate('cloud:%s\n' % password)

    @staticmethod
    def restart_networking():
        if distro == 'debian':
            subprocess.call(['/etc/init.d/networking', 'restart'])
        elif distro == 'rhel':
            subprocess.call(['/bin/systemctl', 'restart', 'network'])
            pass

    @staticmethod
    def change_ip(interfaces, dns):
        if distro == 'debian':
            change_ip_ubuntu(interfaces, dns)
        elif distro == 'rhel':
            change_ip_rhel(interfaces, dns)

    @staticmethod
    def set_time(time):
        Context._linux_set_time(float(time))
        try:
            subprocess.call(['/etc/init.d/ntp', 'restart'])
        except:
            pass

    @staticmethod
    def set_hostname(hostname):
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

    @staticmethod
    def mount_store(host, username, password):
        data = {'host': host, 'username': username, 'password': password}
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
        filelist = ([
            '/root/.bash_history'
            '/home/cloud/.bash_history'
            '/root/.ssh'
            '/home/cloud/.ssh']
            + glob('/etc/ssh/ssh_host_*'))
        for f in filelist:
            rmtree(f, ignore_errors=True)

        subprocess.call(('/usr/bin/ssh-keygen', '-A'))

    @staticmethod
    def start_access_server():
        try:
            subprocess.call(('/sbin/start', 'ssh'))
        except OSError:
            subprocess.call(('/bin/systemctl', 'start', 'sshd.service'))

    @staticmethod
    def append(data, filename, chunk_number, uuid):
        if chunk_number == 0:
            flag = "w"
        else:
            flag = "a"
        with open(filename, flag) as myfile:
            myfile.write(data)

    @staticmethod
    def update(filename, executable, checksum, uuid):
        new_dir = working_directory + '.new'
        old_dir = working_directory + '.old.%s' % uuid
        with open(filename, "r") as f:
            data = f.read()
            local_checksum = md5(data).hexdigest()
            if local_checksum != checksum:
                raise Exception("Checksum missmatch the file is damaged.")
            decoded = StringIO(decodestring(data))
        try:
            tar = tarfile.TarFile.open("dummy", fileobj=decoded, mode='r|gz')
            tar.extractall(new_dir)
        except tarfile.ReadError as e:
            logger.error(e)
        move(working_directory, old_dir)
        move(new_dir, working_directory)
        logger.info("Transfer completed!")
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

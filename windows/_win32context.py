#!/usr/bin/env python
# -*- coding: utf-8 -*-

from os.path import join

import logging
import tarfile
from StringIO import StringIO
from base64 import decodestring
from hashlib import md5
from datetime import datetime
import win32api
import wmi
import netifaces

from twisted.internet import reactor

from .network import change_ip_windows
from context import BaseContext


working_directory = r"C:\circle"

logger = logging.getLogger()


class Context(BaseContext):

    @staticmethod
    def change_password(password):
        from win32com import adsi
        ads_obj = adsi.ADsGetObject('WinNT://localhost/%s,user' % 'cloud')
        ads_obj.Getinfo()
        ads_obj.SetPassword(password)

    @staticmethod
    def restart_networking():
        pass

    @staticmethod
    def change_ip(interfaces, dns):
        change_ip_windows(interfaces, dns)

    @staticmethod
    def set_time(time):
        t = datetime.utcfromtimestamp(float(time))
        win32api.SetSystemTime(t.year, t.month, 0, t.day, t.hour,
                               t.minute, t.second, 0)

    @staticmethod
    def set_hostname(hostname):
        wmi.WMI().Win32_ComputerSystem()[0].Rename(hostname)

    @staticmethod
    def mount_store(host, username, password):
        import notify
        url = 'cifs://%s:%s@%s/%s' % (username, password, host, username)
        for c in notify.clients:
            logger.debug("sending url %s to client %s", url, unicode(c))
            c.sendLine(url.encode())

    @staticmethod
    def get_keys():
        pass

    @staticmethod
    def add_keys(keys):
        pass

    @staticmethod
    def del_keys(keys):
        pass

    @staticmethod
    def cleanup():
        # TODO
        pass

    @staticmethod
    def start_access_server():
        # TODO
        pass

    @staticmethod
    def append(data, filename, chunk_number, uuid):
        if chunk_number == 0:
            flag = "w"
        else:
            flag = "a"
        with open(filename, flag) as myfile:
            myfile.write(data)

    @staticmethod
    def _update_registry(dir, executable):
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
    def update(filename, executable, checksum, uuid):
        with open(filename, "r") as f:
            data = f.read()
            local_checksum = md5(data).hexdigest()
            if local_checksum != checksum:
                raise Exception("Checksum missmatch the file is damaged.")
            decoded = StringIO(decodestring(data))
        try:
            tar = tarfile.TarFile.open("dummy", fileobj=decoded, mode='r|gz')
            tar.extractall(working_directory)
        except tarfile.ReadError as e:
            logger.error(e)
        logger.info("Transfer completed!")
        Context._update_registry(working_directory, executable)
        logger.info('Updated')
        reactor.stop()

    @staticmethod
    def ipaddresses():
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
            with open(join(working_directory, 'version.txt')) as f:
                return f.readline()
        except IOError:
            return None

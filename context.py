""" This is the defautl context file. It replaces the Context class
    to the platform specific one.
"""
import platform
from os.path import exists


def _get_virtio_device():
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


def get_context():
    system = platform.system()
    if system == "Windows":
        from windows._win32context import Context
    elif system == "Linux":
        from linux._linuxcontext import Context
    else:
        raise NotImplementedError("Platform %s is not supported.", system)
    return Context


def get_serial():
    system = platform.system()
    port = None
    if system == 'Windows':
        port = _get_virtio_device()
        if port:
            from windows.win32virtio import SerialPort
        else:
            from twisted.internet.serialport import SerialPort
            import pythoncom
            pythoncom.CoInitialize()
            port = r'\\.\COM1'
    elif system == "Linux":
        port = "/dev/virtio-ports/agent"
        if exists(port):
            from linux.posixvirtio import SerialPort
        else:
            from twisted.internet.serialport import SerialPort
            port = '/dev/ttyS0'
    else:
        raise NotImplementedError("Platform %s is not supported.", system)
    return (SerialPort, port)


class BaseContext(object):
    @staticmethod
    def change_password(password):
        pass

    @staticmethod
    def restart_networking():
        pass

    @staticmethod
    def change_ip(interfaces, dns):
        pass

    @staticmethod
    def set_time(time):
        pass

    @staticmethod
    def set_hostname(hostname):
        pass

    @staticmethod
    def mount_store(host, username, password):
        pass

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
        pass

    @staticmethod
    def start_access_server():
        pass

    @staticmethod
    def append(data, filename, chunk_number, uuid):
        pass

    @staticmethod
    def update(filename, executable, checksum, uuid):
        pass

    @staticmethod
    def ipaddresses():
        pass

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

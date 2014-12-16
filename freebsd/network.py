import netifaces
from netaddr import IPNetwork
import fileinput
import logging
import subprocess

logger = logging.getLogger()

interfaces_file = '/etc/rc.conf.d/ifconfig_'

def get_interfaces_freebsd(interfaces):
    for ifname in netifaces.interfaces():
        mac = netifaces.ifaddresses(ifname)[18][0]['addr']
        conf = interfaces.get(mac.upper())
        if conf:
            yield ifname, conf


def remove_interfaces_ubuntu(devices):
    delete_device = False

    for line in fileinput.input(interfaces_file, inplace=True):
        line = line.rstrip()
        words = line.split()

        if line.startswith('#') or line == '' or line.isspace() or not words:
            # keep line
            print line
            continue

        if (words[0] in ('auto', 'allow-hotplug') and
                words[1].split(':')[0] in devices):
            # remove line
            continue

        if words[0] == 'iface':
            ifname = words[1].split(':')[0]
            if ifname in devices:
                # remove line
                delete_device = True
                continue
            else:
                delete_device = False

        if line[0] in (' ', '\t') and delete_device:
            # remove line
            continue

        # keep line
        print line


def change_ip_freebsd(interfaces, dns):
    data = list(get_interfaces_freebsd(interfaces))

    for ifname, conf in data:
        subprocess.call(('/usr/sbin/service','netif', 'stop', ifname))
    #remove_interfaces_ubuntu(dict(data).keys())

    with open(interfaces_file, 'a') as f:
        for ifname, conf in data:
            ipv4_alias_counter = ipv6_alias_counter = 0
            f.write('auto %s\n' % ifname)
            for i in conf['addresses']:
                ip_with_prefix = IPNetwork(i)
                prefixlen = ip_with_prefix.prefixlen
                ip = ip_with_prefix.ip
                alias = ifname
                if ip.version == 6:
                    if ipv6_alias_counter > 0:
                        alias = '%s:%d' % (ifname, ipv6_alias_counter)
                    ipv6_alias_counter += 1
                else:
                    if ipv4_alias_counter > 0:
                        alias = '%s:%d' % (ifname, ipv4_alias_counter)
                    ipv4_alias_counter += 1

                f.write(
                    'iface %(ifname)s %(proto)s static\n'
                    '    address %(ip)s\n'
                    '    netmask %(prefixlen)d\n'
                    '    gateway %(gw)s\n'
                    '    dns-nameservers %(dns)s\n' % {
                        'ifname': alias,
                        'proto': 'inet6' if ip.version == 6 else 'inet',
                        'ip': ip,
                        'prefixlen': prefixlen,
                        'gw': conf['gw6' if ip.version == 6 else 'gw4'],
                        'dns': dns})
    for ifname, conf in data:
        subprocess.call(('/sbin/ifup', ifname))


# example:
# change_ip_ubuntu({
#    u'02:00:00:02:A3:E8': {
#        u'gw4': u'10.1.0.254', 'gw6': '2001::ffff',
#        u'addresses': [u'10.1.0.84/24', '10.1.0.1/24', '2001::1/48']},
#    u'02:00:00:02:A3:E9': {
#        u'gw4': u'10.255.255.1', u'addresses': [u'10.255.255.9']}},
#    '8.8.8.8')


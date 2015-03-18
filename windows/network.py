from netaddr import IPNetwork, IPAddress
import logging
from subprocess import PIPE, Popen

logger = logging.getLogger()

interfaces_file = '/etc/network/interfaces'
ifcfg_template = '/etc/sysconfig/network-scripts/ifcfg-%s'

# example:
# change_ip_ubuntu({
#    u'02:00:00:02:A3:E8': {
#        u'gw4': u'10.1.0.254', 'gw6': '2001::ffff',
#        u'addresses': [u'10.1.0.84/24', '10.1.0.1/24', '2001::1/48']},
#    u'02:00:00:02:A3:E9': {
#        u'gw4': u'10.255.255.1', u'addresses': [u'10.255.255.9']}},
#    '8.8.8.8')


class IPAddress2(IPNetwork):
    def key(self):
        return self._module.version, self._value, self._prefixlen


def check_output2(cmd, shell=False):
    try:
        p = Popen(cmd, shell=shell,
                  stderr=PIPE, stdout=PIPE, stdin=PIPE)
        stdout, stderr = p.communicate()
        logger.info('%s: %s, %s', cmd, stdout, stderr)
        return stdout
    except:
        logger.exception(
            'Unhandled exception in %s: ', cmd)


def get_interfaces_windows(interfaces):
    import wmi
    nics = wmi.WMI().Win32_NetworkAdapterConfiguration(IPEnabled=True)
    for nic in nics:
        conf = interfaces.get(nic.MACAddress)
        if conf:
            yield nic, conf


def change_ip_windows(interfaces, dns):
    for nic, conf in get_interfaces_windows(interfaces):
        link_local = IPNetwork('fe80::/16')
        new_addrs = set([IPAddress2(ip) for ip in conf['addresses']])
        old_addrs = set([IPAddress2('%s/%s' % (ip, nic.IPSubnet[i]))
                         for i, ip in enumerate(nic.IPAddress)
                         if IPAddress(ip) not in link_local])

        addrs_add = new_addrs - old_addrs
        addrs_del = old_addrs - new_addrs

        changed = (addrs_add or addrs_del or
                   set(nic.DefaultIPGateway) != set(
                       [conf.get('gw4'), conf.get('gw6')]))
        if changed:
            logger.info('new config for <%s(%s)>: %s', nic.Description,
                        nic.MACAddress, ', '.join(conf['addresses']))

            for ip in addrs_add:
                logger.info('add %s (%s)', ip, nic.Description)
                if ip.version == 6:
                    cmd = (
                        'netsh interface ipv6 add address '
                        'interface=%s address=%s'
                        % (nic.InterfaceIndex, ip))
                else:
                    cmd = (
                        'netsh interface ipv4 add address '
                        '%s %s %s'
                        % (nic.InterfaceIndex, ip.ip, ip.netmask))

                check_output2(cmd, shell=True)

            for ip in addrs_del:
                proto = 'ipv6' if ip.version == 6 else 'ipv4'
                logger.info('del %s (%s)', ip, nic.Description)
                check_output2(
                    'netsh interface %s delete address '
                    '%s %s'
                    % (proto, nic.InterfaceIndex, ip.ip), shell=True)

            # default gw4
            if conf.get('gw4'):
                check_output2(
                    'netsh interface ip del route 0.0.0.0/0 interface=%s'
                    % nic.InterfaceIndex, shell=True)
                check_output2(
                    'netsh interface ip add route 0.0.0.0/0 interface=%s %s'
                    % (nic.InterfaceIndex, conf.get('gw4')), shell=True)

            # default gw6
            if conf.get('gw6'):
                check_output2(
                    'netsh interface ipv6 del route ::/0 interface=%s'
                    % nic.InterfaceIndex, shell=True)
                check_output2(
                    'netsh interface ipv6 add route ::/0 interface=%s %s'
                    % (nic.InterfaceIndex, conf.get('gw6')), shell=True)

            # DNS
            check_output2('netsh interface ipv4 add dnsserver %s '
                          'address=%s index=1'
                          % (nic.InterfaceIndex, dns), shell=True)

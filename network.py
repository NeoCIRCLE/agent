import netifaces
from netaddr import IPNetwork, IPAddress
import fileinput
import logging
from subprocess import check_output, CalledProcessError

logger = logging.getLogger()

interfaces_file = '/etc/network/interfaces'
ifcfg_template = '/etc/sysconfig/network-scripts/ifcfg-%s'


def get_interfaces_linux(interfaces):
    for ifname in netifaces.interfaces():
        mac = netifaces.ifaddresses(ifname)[17][0]['addr']
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
            if words[1].split(':')[0] in devices:
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


def change_ip_ubuntu(interfaces, dns):
    data = list(get_interfaces_linux(interfaces))
    remove_interfaces_ubuntu(dict(data).keys())

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


# example:
# change_ip_ubuntu({
#    u'02:00:00:02:A3:E8': {
#        u'gw4': u'10.1.0.254', 'gw6': '2001::ffff',
#        u'addresses': [u'10.1.0.84/24', '10.1.0.1/24', '2001::1/48']},
#    u'02:00:00:02:A3:E9': {
#        u'gw4': u'10.255.255.1', u'addresses': [u'10.255.255.9']}},
#    '8.8.8.8')


def change_ip_rhel(interfaces, dns):
    for ifname, conf in get_interfaces_linux(interfaces):
        with open(ifcfg_template % ifname,
                  'w') as f:
            f.write('DEVICE=%s\n'
                    'BOOTPROTO=none\n'
                    'USERCTL=no\n'
                    'ONBOOT=yes\n' % ifname)
            for i in conf['addresses']:
                ip_with_prefix = IPNetwork(i)
                ip = ip_with_prefix.ip
                if ip.version == 6:
                    f.write('IPV6INIT=yes\n'
                            'IPV6ADDR=%(ip)s/%(prefixlen)d\n'
                            'IPV6_DEFAULTGW=%(gw)s\n' % {
                                'ip': ip,
                                'prefixlen': ip_with_prefix.prefixlen,
                                'gw': conf['gw6']})
                else:
                    f.write('NETMASK=%(netmask)s\n'
                            'IPADDR=%(ip)s\n'
                            'GATEWAY=%(gw)s\n' % {
                                'ip': ip,
                                'netmask': str(ip_with_prefix.netmask),
                                'gw': conf['gw4']})


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
        new_addrs = [IPNetwork(ip) for ip in conf['addresses']]
        new_addrs_str = set(str(ip) for ip in new_addrs)
        old_addrs = [IPNetwork('%s/%s' % (ip, nic.IPSubnet[i]))
                     for i, ip in enumerate(nic.IPAddress)
                     if IPAddress(ip) not in link_local]
        old_addrs_str = set(str(ip) for ip in old_addrs)

        changed = (
            new_addrs_str != old_addrs_str or
            set(nic.DefaultIPGateway) != set([conf['gw4'], conf['gw6']]))
        if changed or 1:
            logger.info('new config for <%s(%s)>: %s', nic.Description,
                        nic.MACAddress, ', '.join(new_addrs_str))
            # IPv4
            ipv4_addrs = [str(ip.ip) for ip in new_addrs
                          if ip.version == 4]
            ipv4_masks = [str(ip.netmask) for ip in new_addrs
                          if ip.version == 4]
            logger.debug('<%s>.EnableStatic(%s, %s) called', nic.Description,
                         ipv4_addrs, ipv4_masks)
            retval = nic.EnableStatic(
                IPAddress=ipv4_addrs, SubnetMask=ipv4_masks)
            assert retval == (0, )

            nic.SetGateways(DefaultIPGateway=[conf['gw4']])
            assert retval == (0, )

            # IPv6
            for ip in new_addrs:
                if ip.version == 6 and str(ip) not in old_addrs_str:
                    logger.debug('add %s (%s)', ip, nic.Description)
                    check_output(
                        'netsh interface ipv6 add address '
                        'interface=%s address=%s'
                        % (nic.InterfaceIndex, ip), shell=True)

            for ip in old_addrs:
                if ip.version == 6 and str(ip) not in new_addrs_str:
                    logger.debug('delete %s (%s)', ip, nic.Description)
                    check_output(
                        'netsh interface ipv6 delete address '
                        'interface=%s address=%s'
                        % (nic.InterfaceIndex, ip.ip), shell=True)

            try:
                check_output('netsh interface ipv6 del route ::/0 interface=%s'
                             % nic.InterfaceIndex, shell=True)
            except CalledProcessError:
                pass
            check_output('netsh interface ipv6 add route ::/0 interface=%s %s'
                         % (nic.InterfaceIndex, conf['gw6']), shell=True)

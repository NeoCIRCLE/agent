from netaddr import IPNetwork, IPAddress
import logging
from subprocess import check_output, PIPE, Popen

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
            set(nic.DefaultIPGateway) != set([conf.get('gw4'), conf('gw6')]))
        if changed or 1:  # TODO
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

            nic.SetGateways(DefaultIPGateway=[conf.get('gw4')])
            assert retval == (0, )

            # IPv6
            for ip in new_addrs:
                if ip.version == 6 and str(ip) not in old_addrs_str:
                    logger.info('add %s (%s)', ip, nic.Description)
                    try:
                        p = Popen((
                            'netsh interface ipv6 add address '
                            'interface=%s address=%s')
                            % (nic.InterfaceIndex, ip), shell=True,
                            stderr=PIPE, stdout=PIPE, stdin=PIPE)
                        logger.info('netsh_add(): %s', p.communicate())
                    except:
                        logger.exception(
                            'Unhandled exception in netsh_add(): ')

            for ip in old_addrs:
                if ip.version == 6 and str(ip) not in new_addrs_str:
                    logger.info('del %s (%s)', ip, nic.Description)
                    try:
                        p = Popen((
                            'netsh interface ipv6 delete address '
                            'interface=%s address=%s')
                            % (nic.InterfaceIndex, ip), shell=True,
                            stderr=PIPE, stdout=PIPE, stdin=PIPE)
                        logger.info('netsh_add(): %s', p.communicate())
                    except:
                        logger.exception(
                            'Unhandled exception in netsh_del(): ')

            # default gw6
            try:
                check_output('netsh interface ipv6 del route ::/0 interface=%s'
                             % nic.InterfaceIndex, shell=True)
            except:
                logger.exception('Unhandled exception:')

            try:
                check_output(
                    'netsh interface ipv6 add route ::/0 interface=%s %s'
                    % (nic.InterfaceIndex, conf.get('gw6')), shell=True)
            except:
                logger.exception('Unhandled exception:')

            # DNS
            try:
                check_output('netsh interface ipv4 add dnsserver %s '
                             'address=%s index=1'
                             % (nic.InterfaceIndex, dns), shell=True)
            except:
                logger.exception('Unhandled exception:')

import netifaces
from netaddr import IPNetwork
import fileinput
import logging
import subprocess
import os
import os.path

logger = logging.getLogger()

rcconf_dir = '/etc/rc.conf.d/'

def get_interfaces_freebsd(interfaces):
    for ifname in netifaces.interfaces():
        if ifname == 'lo0':
            continue # XXXOP: ?
        logger.debug("get_interfaces: " + ifname)
        mac = netifaces.ifaddresses(ifname)[18][0]['addr']
        logger.debug("get_interfaces: " + mac)
        conf = interfaces.get(mac.upper())
        if conf:
            yield ifname, conf


def remove_interfaces_freebsd(devices):
    delete_device = False
    for device in devices:
        if_file = rcconf_dir + device
        if os.path.isfile(if_file):
            logger.debug("remove interface configuration: " + if_file)
            os.unlink(if_file)
        else:
            logger.debug("unable to remove interface configuration: " + if_file)


def change_ip_freebsd(interfaces, dns):
    data = list(get_interfaces_freebsd(interfaces))

    for ifname, conf in data:
        subprocess.call(('/usr/sbin/service','netif', 'stop', ifname))
    remove_interfaces_freebsd(dict(data).keys())

    for device, conf in data:
        if_file = rcconf_dir + "ifconfig_" + device
        with open(if_file, 'w') as f:
            ipv4_alias_counter = ipv6_alias_counter = 0
            route6 = "ipv6_static_routes=\""
            route4 = "static_routes=\""
            for i in conf['addresses']:
                alias=""
                ip_with_prefix = IPNetwork(i)
                ip = ip_with_prefix.ip
                prefixlen = ip_with_prefix.prefixlen
                if ip.version == 6:
                    alias="_ipv6"
                    if ipv6_alias_counter > 0:
                        alias = '_alias%d' % (ipv6_alias_counter-1)
                    ipv6_alias_counter += 1
                    f.write("ifconfig_" + device + alias + "=" +
                        "\"inet6 %(ip)s prefix %(pref)s\"\n" % { 'ip' : ip, 'pref' : prefixlen })
                    route6_name=device+"R"+str(ipv6_alias_counter)+"v6"
                    route6 += route6_name+":"+device+" "
                    f.write("route_"+route6_name+"=\"-net %(netw)s0 -gateway %(gw)s\"\n" % { 'netw' : ip_with_prefix.network, 'gw' : conf['gw6']})
                else:
                    if ipv4_alias_counter > 0:
                        # az aliasok szamanak folytonosnak kell lennie
                        ipv4_alias_counter=ipv6_alias_counter+1
                        alias = '_alias%d' % (ipv4_alias_counter)
                    ipv4_alias_counter += 1
                    f.write("ifconfig_" + device + alias + "=" + "\"inet %(ip)s/%(pref)s\"\n" % { 'ip' : ip, 'pref' : prefixlen })
                    route4_name=device+"R"+str(ipv4_alias_counter)+"v4"
                    route4 += route4_name+":"+device+" "
                    f.write("route_"+route4_name+"=\"-net %(netw)s -gateway %(gw)s\"\n" % { 'netw' : ip_with_prefix.network, 'gw' : conf['gw4']})
                    f.write("defaultrouter=\""+str(conf['gw4'])+"\"\n")
            route4 += "\"\n"
            route6 += "\"\n"
            f.write(route4) 
            f.write(route6) 

    with open("/etc/resolv.conf", "w") as f:
        f.write("nameserver "+dns)

    for ifname, conf in data:
        subprocess.call(('/usr/sbin/service', 'netif', 'start', ifname))

    subprocess.call(('/usr/sbin/service', 'routing', 'start'))


# example:
# change_ip_ubuntu({
#    u'02:00:00:02:A3:E8': {
#        u'gw4': u'10.1.0.254', 'gw6': '2001::ffff',
#        u'addresses': [u'10.1.0.84/24', '10.1.0.1/24', '2001::1/48']},
#    u'02:00:00:02:A3:E9': {
#        u'gw4': u'10.255.255.1', u'addresses': [u'10.255.255.9']}},
#    '8.8.8.8')


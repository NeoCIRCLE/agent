#!/bin/sh

#export LOGLEVEL=DEBUG

pkg install -y devel/git lang/python devel/py-pip sysutils/screen editors/vim-lite security/sudo

grep "^cloud:" /etc/passwd > /dev/null
ret=$?
if [ $ret -ne 0 ]
then
	# create the required backdoor user
	pw user add cloud -m
	pw group mod wheel -m cloud
fi

sed -i '.orig' -e 's/# \(%wheel ALL=(ALL) ALL\)/\1/g' /usr/local/etc/sudoers

if [ ! -d /usr/ports ]
then
	git clone https://github.com/HardenedBSD/freebsd-ports.git /usr/ports
fi

if [ ! -d /store ]
then
	mkdir -p /store
fi

if [ ! -d /root/agent ]
then
	cd /root
	git clone https://github.com/opntr/bme-cloud-circle-agent.git agent
fi

grep "If a service" /etc/rc.subr
ret=$?
if [ $ret -eq 0 ]
then
	echo "patching /etc/rc.subr ..."
	(
	cd /etc
	patch -p0 < /root/agent/bootstrap/freebsd/fix-rc.subr.diff
	)
fi

cd /root/agent
if [ -d /usr/local/etc/rc.d ]
then
	cp bootstrap/freebsd/rc.d/circle_agent /usr/local/etc/rc.d
fi

if [ ! -f /etc/rc.conf.d/circle_agent ]
then
	echo 'circle_agent_enable="YES"' > /etc/rc.conf.d/circle_agent
fi

service circle_agent start

#!/bin/sh

export LOGLEVEL=DEBUG

pkg install -y devel/git lang/python devel/py-pip sysutils/screen editors/vim-lite

grep "^cloud:" /etc/passwd > /dev/null
ret=$?
if [ $ret -ne 0 ]
then
	# create the required backdoor user
	pw user add cloud -m
	pw group mod wheel -m cloud
fi

if [ ! -d /usr/ports ]
then
	git clone https://github.com/HardenedBSD/freebsd-ports.git /usr/ports
fi

if [ ! -d /root/agent ]
then
	cd /root
	git clone https://github.com/opntr/bme-cloud-circle-agent.git agent
fi

cd /root/agent

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

python agent.py

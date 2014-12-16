#!/bin/sh

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
	git clone https://git.ik.bme.hu/circle/agent.git
fi

cd /root/agent
python agent.py

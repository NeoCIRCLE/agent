# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Virtio-Serial Port Protocol
"""

# system imports
import os

# dependent on pyserial ( http://pyserial.sf.net/ )
# only tested w/ 1.18 (5 Dec 2002)

# twisted imports
from twisted.internet import abstract, fdesc


class SerialPort(abstract.FileDescriptor):
    """
    A select()able serial device, acting as a transport.
    """

    connected = 1

    def __init__(self, protocol, deviceNameOrPortNumber, reactor):
        abstract.FileDescriptor.__init__(self, reactor)
        self.port = deviceNameOrPortNumber
        self._serial = os.open(
            self.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        self.reactor = reactor
        self.protocol = protocol
        self.protocol.makeConnection(self)
        self.startReading()

    def fileno(self):
        return self._serial

    def writeSomeData(self, data):
        """
        Write some data to the serial device.
        """
        return fdesc.writeToFD(self.fileno(), data)

    def doRead(self):
        """
        Some data's readable from serial device.
        """
        return fdesc.readFromFD(self.fileno(), self.protocol.dataReceived)

    def connectionLost(self, reason):
        """
        Called when the serial port disconnects.

        Will call C{connectionLost} on the protocol that is handling the
        serial data.
        """
        abstract.FileDescriptor.connectionLost(self, reason)
        os.close(self._serial)
        self.protocol.connectionLost(reason)

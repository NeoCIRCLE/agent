# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Serial port support for Windows.

Requires PySerial and pywin32.
"""

# system imports

import win32file
import win32event
import win32con

# twisted imports
from twisted.internet import abstract

# sibling imports
import logging
logger = logging.getLogger()


class SerialPort(abstract.FileDescriptor):

    """A serial device, acting as a transport, that uses a win32 event."""

    connected = 1

    def __init__(self, protocol, deviceNameOrPortNumber, reactor):
        self.hComPort = win32file.CreateFile(
            deviceNameOrPortNumber,
            win32con.GENERIC_READ | win32con.GENERIC_WRITE,
            0,  # exclusive access
            None,  # no security
            win32con.OPEN_EXISTING,
            win32con.FILE_ATTRIBUTE_NORMAL | win32con.FILE_FLAG_OVERLAPPED,
            0)
        self.reactor = reactor
        self.protocol = protocol
        self.outQueue = []
        self.closed = 0
        self.closedNotifies = 0
        self.writeInProgress = 0

        self.protocol = protocol
        self._overlappedRead = win32file.OVERLAPPED()
        self._overlappedRead.hEvent = win32event.CreateEvent(None, 1, 0, None)
        self._overlappedWrite = win32file.OVERLAPPED()
        self._overlappedWrite.hEvent = win32event.CreateEvent(None, 0, 0, None)

        self.reactor.addEvent(
            self._overlappedRead.hEvent,
            self,
            'serialReadEvent')
        self.reactor.addEvent(
            self._overlappedWrite.hEvent,
            self,
            'serialWriteEvent')

        self.protocol.makeConnection(self)
        self._finishPortSetup()

    def _finishPortSetup(self):
        """
        Finish setting up the serial port.

        This is a separate method to facilitate testing.
        """
        rc, self.read_buf = win32file.ReadFile(self.hComPort,
                                               win32file.AllocateReadBuffer(1),
                                               self._overlappedRead)

    def serialReadEvent(self):
        # get that character we set up
        try:
            n = win32file.GetOverlappedResult(
                self.hComPort,
                self._overlappedRead,
                0)
        except:
            import time
            time.sleep(10)
            n = 0
        if n:
            first = str(self.read_buf[:n])
            # now we should get everything that is already in the buffer (max
            # 4096)
            win32event.ResetEvent(self._overlappedRead.hEvent)
            rc, buf = win32file.ReadFile(self.hComPort,
                                         win32file.AllocateReadBuffer(4096),
                                         self._overlappedRead)
            n = win32file.GetOverlappedResult(
                self.hComPort,
                self._overlappedRead,
                1)
            # handle all the received data:
            self.protocol.dataReceived(first + str(buf[:n]))
        # set up next one
        win32event.ResetEvent(self._overlappedRead.hEvent)
        rc, self.read_buf = win32file.ReadFile(self.hComPort,
                                               win32file.AllocateReadBuffer(1),
                                               self._overlappedRead)

    def write(self, data):
        if data:
            if self.writeInProgress:
                self.outQueue.append(data)
                logger.debug("added to queue")
            else:
                self.writeInProgress = 1
                win32file.WriteFile(self.hComPort, data, self._overlappedWrite)
                logger.debug("Writed to file")

    def serialWriteEvent(self):
        try:
            dataToWrite = self.outQueue.pop(0)
        except IndexError:
            self.writeInProgress = 0
            return
        else:
            win32file.WriteFile(
                self.hComPort,
                dataToWrite,
                self._overlappedWrite)

    def connectionLost(self, reason):
        """
        Called when the serial port disconnects.

        Will call C{connectionLost} on the protocol that is handling the
        serial data.
        """
        self.reactor.removeEvent(self._overlappedRead.hEvent)
        self.reactor.removeEvent(self._overlappedWrite.hEvent)
        abstract.FileDescriptor.connectionLost(self, reason)
        win32file.CloseHandle(self.hComPort)
        self.protocol.connectionLost(reason)

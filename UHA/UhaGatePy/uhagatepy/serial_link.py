"""The serial port to ELECON (115200 8N1), non-blocking, with disconnect detection.

The gateway owns the port exclusively. When the USB adapter disappears, `read()` / `write()` raise
LinkError and the gateway closes the link and retries `open()` every few seconds.
"""
import serial

BAUDRATE = 115200


class LinkError(Exception):
    """The serial link is lost (adapter unplugged, I/O error)."""


class SerialLink:
    def __init__(self, path: str) -> None:
        self.path = path
        self.last_error = ""
        self._port = None

    @property
    def is_open(self) -> bool:
        return self._port is not None

    def fileno(self) -> int:
        return self._port.fileno()

    def open(self) -> bool:
        """Try to open the port. Returns False and sets last_error when it is not possible."""
        self.close()
        try:
            port = serial.Serial(
                self.path, BAUDRATE, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0,           # read() never waits, the event loop tells us when data is there
                write_timeout=1,     # a stuck write must not block the loop for long
                exclusive=True)      # nobody else may open the port while we hold it
            port.reset_input_buffer()   # drop what arrived before (re)opening
        except (serial.SerialException, OSError, ValueError) as e:
            self.last_error = str(e)
            return False
        self._port = port
        self.last_error = ""
        return True

    def close(self) -> None:
        if self._port is not None:
            try:
                self._port.close()
            except (serial.SerialException, OSError):
                pass
            self._port = None

    def read(self) -> bytes:
        """Return the bytes that are available now (b"" when none)."""
        try:
            # when the adapter is gone the port still reports "readable" and pyserial raises here
            return self._port.read(4096)
        except (serial.SerialException, OSError) as e:
            self.last_error = str(e)
            raise LinkError(self.last_error) from e

    def write(self, data: bytes) -> bool:
        """Send bytes. False if they could not be sent now (link kept); LinkError if the link is lost."""
        try:
            return self._port.write(data) == len(data)
        except serial.SerialTimeoutException:
            self.last_error = "write timeout"
            return False
        except (serial.SerialException, OSError) as e:
            self.last_error = str(e)
            raise LinkError(self.last_error) from e

#include "serial_link.h"

#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <termios.h>
#include <unistd.h>

static std::string errno_text(const char* what)
{
    return std::string(what) + ": " + strerror(errno);
}

bool SerialLink::open()
{
    close();
    int fd = ::open(mPath.c_str(), O_RDWR | O_NOCTTY | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0)
    {
        mLastError = errno_text("open");
        return false;
    }

    struct termios t;
    if (tcgetattr(fd, &t) != 0)
    {
        mLastError = errno_text("tcgetattr");
        ::close(fd);
        return false;
    }
    cfmakeraw(&t);
    cfsetspeed(&t, B115200);
    t.c_cflag |= CLOCAL | CREAD;
    // VMIN=1 with O_NONBLOCK: no data -> EAGAIN, hung-up tty -> 0 (EOF). With VMIN=0 both return 0.
    t.c_cc[VMIN] = 1;
    t.c_cc[VTIME] = 0;
    if (tcsetattr(fd, TCSANOW, &t) != 0)
    {
        mLastError = errno_text("tcsetattr");
        ::close(fd);
        return false;
    }
    ioctl(fd, TIOCEXCL);        // no other process may open the port while we hold it
    tcflush(fd, TCIOFLUSH);     // drop stale bytes from before the (re)open

    mFd = fd;
    mLastError.clear();
    return true;
}

void SerialLink::close()
{
    if (mFd >= 0)
    {
        ::close(mFd);
        mFd = -1;
    }
}

ssize_t SerialLink::read(uint8_t* buf, size_t size)
{
    if (mFd < 0) return -1;
    ssize_t n = ::read(mFd, buf, size);
    if (n > 0) return n;
    if (n == 0)
    {
        // poll() reported readable but there is no data: the tty was hung up (adapter removed)
        mLastError = "end of file (device disconnected)";
        return -1;
    }
    if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) return 0;
    mLastError = errno_text("read");
    return -1;
}

int SerialLink::write(const uint8_t* data, size_t size)
{
    if (mFd < 0) return -1;
    ssize_t n = ::write(mFd, data, size);
    if (n == (ssize_t)size) return 1;
    if (n >= 0 || errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)
    {
        mLastError = "write incomplete";
        return 0;
    }
    mLastError = errno_text("write");
    return -1;
}

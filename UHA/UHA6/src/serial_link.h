// Non-blocking serial port (115200 8N1 raw) used from the poll() loop.
// Detects disconnect of the USB adapter (EOF / EIO / ENODEV / POLLHUP) so the caller can reopen it.
#ifndef UHA6_SERIAL_LINK_H
#define UHA6_SERIAL_LINK_H

#include <cstddef>
#include <cstdint>
#include <string>
#include <sys/types.h>

class SerialLink
{
public:
    explicit SerialLink(std::string path) : mPath(std::move(path)) {}
    ~SerialLink() { close(); }

    bool open();            // false on failure, see lastError()
    void close();
    bool isOpen() const { return mFd >= 0; }
    int fd() const { return mFd; }
    const std::string& path() const { return mPath; }
    const std::string& lastError() const { return mLastError; }

    // > 0 bytes read, 0 nothing available, -1 link lost (see lastError()).
    ssize_t read(uint8_t* buf, size_t size);
    // 1 written, 0 not written (would block, link kept), -1 link lost.
    int write(const uint8_t* data, size_t size);

private:
    std::string mPath;
    std::string mLastError;
    int mFd = -1;
};

#endif

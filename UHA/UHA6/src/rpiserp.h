// RPISERP framing: 0x7F 0xAA | len | id_hi id_lo | data (len-2 bytes, <= 8) | checksum
// checksum = 8-bit sum of all preceding bytes of the frame (from 0x7F).
// Same rules as UHA5 rpiserp.c, but the parser is a pure, single-threaded object
// (no receiver thread, no shared ring buffer) and keeps partial frames across reads.
#ifndef UHA6_RPISERP_H
#define UHA6_RPISERP_H

#include <cstddef>
#include <cstdint>
#include <functional>
#include <vector>

#define RPISERP_START_B1        0x7F
#define RPISERP_START_B2        0xAA
#define RPISERP_ID_LENGTH       2
#define RPISERP_MAX_DATA_LENGTH 8
#define RPISERP_MAX_FRAME       (RPISERP_MAX_DATA_LENGTH + RPISERP_ID_LENGTH + 4)

struct RpiPacket
{
    uint16_t id = 0;
    uint8_t dlc = 0;
    uint8_t data[RPISERP_MAX_DATA_LENGTH] = {0};   // unused bytes are zero (as in UHA5)
};

struct RpiParserStats
{
    uint64_t rxBytes = 0;
    uint64_t packets = 0;
    uint64_t checksumErrors = 0;
    uint64_t lengthErrors = 0;     // len byte outside 2..10
    uint64_t discardedBytes = 0;   // bytes outside any valid frame
};

class RpiserpParser
{
public:
    using Handler = std::function<void(const RpiPacket&)>;

    // Append received bytes and call onPacket for every complete valid frame.
    void feed(const uint8_t* bytes, size_t n, const Handler& onPacket);
    // Drop any partial frame (e.g. after the serial link was reopened).
    void reset() { mBuf.clear(); }
    const RpiParserStats& stats() const { return mStats; }

private:
    std::vector<uint8_t> mBuf;
    std::vector<RpiPacket> mReady;
    RpiParserStats mStats;
};

uint8_t rpiserp_checksum(const uint8_t* data, size_t length);

// Encode a packet into out (at least RPISERP_MAX_FRAME bytes). Returns frame length, 0 if dlc > 8.
size_t rpiserp_encode(const RpiPacket& packet, uint8_t* out);

#endif

#include "rpiserp.h"

#include <cstring>

uint8_t rpiserp_checksum(const uint8_t* data, size_t length)
{
    uint8_t sum = 0;
    for (size_t i = 0; i < length; i++) sum += data[i];
    return sum;
}

size_t rpiserp_encode(const RpiPacket& packet, uint8_t* out)
{
    if (packet.dlc > RPISERP_MAX_DATA_LENGTH) return 0;
    out[0] = RPISERP_START_B1;
    out[1] = RPISERP_START_B2;
    out[2] = packet.dlc + RPISERP_ID_LENGTH;
    out[3] = (packet.id >> 8) & 0xFF;
    out[4] = packet.id & 0xFF;
    memcpy(&out[5], packet.data, packet.dlc);
    out[packet.dlc + 5] = rpiserp_checksum(out, packet.dlc + 5);
    return packet.dlc + 6;
}

void RpiserpParser::feed(const uint8_t* bytes, size_t n, const Handler& onPacket)
{
    mStats.rxBytes += n;
    mBuf.insert(mBuf.end(), bytes, bytes + n);

    const size_t size = mBuf.size();
    size_t i = 0;
    while (true)
    {
        // look for the start sequence
        while (i + 1 < size && !(mBuf[i] == RPISERP_START_B1 && mBuf[i + 1] == RPISERP_START_B2))
        {
            i++;
            mStats.discardedBytes++;
        }
        if (i + 1 >= size)
        {
            // at most one byte left: keep it only if it may be the first half of a start sequence
            if (i < size && mBuf[i] != RPISERP_START_B1)
            {
                i++;
                mStats.discardedBytes++;
            }
            break;
        }
        if (i + 3 > size) break;   // length byte not received yet

        const uint8_t len = mBuf[i + 2];
        if (len < RPISERP_ID_LENGTH || len > RPISERP_ID_LENGTH + RPISERP_MAX_DATA_LENGTH)
        {
            mStats.lengthErrors++;
            mStats.discardedBytes++;
            i++;
            continue;
        }
        if (i + len + 4 > size) break;   // wait for the rest of the frame

        if (rpiserp_checksum(&mBuf[i], len + 3) != mBuf[i + len + 3])
        {
            mStats.checksumErrors++;
            mStats.discardedBytes++;
            i++;
            continue;
        }

        RpiPacket packet;
        packet.id = (uint16_t)(mBuf[i + 3] << 8 | mBuf[i + 4]);
        packet.dlc = len - RPISERP_ID_LENGTH;
        memcpy(packet.data, &mBuf[i + 5], packet.dlc);
        mStats.packets++;
        i += len + 4;
        mReady.push_back(packet);
    }
    mBuf.erase(mBuf.begin(), mBuf.begin() + i);

    // dispatch after the buffer is consistent, so the handler may safely call reset()
    std::vector<RpiPacket> ready;
    ready.swap(mReady);
    for (const RpiPacket& packet : ready) onPacket(packet);
}

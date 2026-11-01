// Unit tests for the portable part of UhaGate6 (parser, encoder, JSON outputs, event log line).
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "cJSON.h"
#include "event_log.h"
#include "outputs.h"
#include "rpiserp.h"
#include "uha_vars.h"

static int sFailures = 0;
#define CHECK(cond)                                                          \
    do {                                                                     \
        if (!(cond)) {                                                       \
            printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);           \
            sFailures++;                                                     \
        }                                                                    \
    } while (0)

static std::vector<uint8_t> frame(uint16_t id, std::vector<uint8_t> data)
{
    RpiPacket p;
    p.id = id;
    p.dlc = (uint8_t)data.size();
    memcpy(p.data, data.data(), data.size());
    uint8_t out[RPISERP_MAX_FRAME];
    size_t n = rpiserp_encode(p, out);
    return std::vector<uint8_t>(out, out + n);
}

struct Collector
{
    RpiserpParser parser;
    std::vector<RpiPacket> packets;
    void feed(const std::vector<uint8_t>& bytes, size_t chunk = 1000)
    {
        for (size_t i = 0; i < bytes.size(); i += chunk)
        {
            size_t n = std::min(chunk, bytes.size() - i);
            parser.feed(&bytes[i], n, [this](const RpiPacket& p) { packets.push_back(p); });
        }
    }
};

static void append(std::vector<uint8_t>& a, const std::vector<uint8_t>& b) { a.insert(a.end(), b.begin(), b.end()); }

static void test_encode()
{
    // RTC sync frame as sent by UHA5: 7F AA 06 00 51 d0 d1 d2 d3 checksum
    std::vector<uint8_t> f = frame(0x51, {0x01, 0x02, 0x03, 0x04});
    std::vector<uint8_t> expected = {0x7F, 0xAA, 0x06, 0x00, 0x51, 0x01, 0x02, 0x03, 0x04, 0};
    expected[9] = rpiserp_checksum(expected.data(), 9);
    CHECK(f == expected);
    CHECK(expected[9] == (uint8_t)(0x7F + 0xAA + 0x06 + 0x51 + 1 + 2 + 3 + 4));

    RpiPacket tooLong;
    tooLong.dlc = 9;
    uint8_t out[RPISERP_MAX_FRAME + 4];
    CHECK(rpiserp_encode(tooLong, out) == 0);
}

static void test_single_and_split()
{
    std::vector<uint8_t> f = frame(0x221, {0x00, 0x0A, 0xFF, 0x9C});   // VAR_BAT_SOC = -100
    for (size_t chunk : {1000, 1, 2, 3, 5})
    {
        Collector c;
        c.feed(f, chunk);
        CHECK(c.packets.size() == 1);
        if (c.packets.size() != 1) continue;
        CHECK(c.packets[0].id == 0x221);
        CHECK(c.packets[0].dlc == 4);
        CHECK((short)(c.packets[0].data[2] << 8 | c.packets[0].data[3]) == -100);
        CHECK(c.parser.stats().discardedBytes == 0);
    }
}

static void test_start_byte_at_chunk_end()
{
    // UHA5 lost the frame when a read ended right after 0x7F
    std::vector<uint8_t> stream = {0x11, 0x22};
    append(stream, frame(0x620, {4, 0, 12, 0, 0, 0, 0, 0}));
    Collector c;
    c.feed(std::vector<uint8_t>(stream.begin(), stream.begin() + 3));   // 11 22 7F
    c.feed(std::vector<uint8_t>(stream.begin() + 3, stream.end()));
    CHECK(c.packets.size() == 1);
    CHECK(c.parser.stats().discardedBytes == 2);
}

static void test_garbage_and_errors()
{
    std::vector<uint8_t> stream = {0x00, 0x7F, 0x00, 0xAA};
    append(stream, frame(0x221, {0, 1, 0, 1}));
    std::vector<uint8_t> bad = frame(0x221, {0, 2, 0, 2});
    bad.back() ^= 0xFF;                                     // wrong checksum
    append(stream, bad);
    append(stream, {0x7F, 0xAA, 0x00, 0x7F, 0xAA, 0x01});   // len 0 and len 1 (crashed UHA5)
    append(stream, {0x7F, 0xAA, 0x0B});                     // len 11 > max
    std::vector<uint8_t> inner = frame(0x221, {0x7F, 0xAA, 0x7F, 0xAA});   // start sequence inside data
    append(stream, inner);
    append(stream, frame(0x123, {}));                       // dlc 0, unknown id

    for (size_t chunk : {1000, 1, 7})
    {
        Collector c;
        c.feed(stream, chunk);
        CHECK(c.packets.size() == 3);
        if (c.packets.size() != 3) continue;
        CHECK(c.packets[0].data[1] == 1);
        CHECK(c.packets[1].data[0] == 0x7F && c.packets[1].data[3] == 0xAA);
        CHECK(c.packets[2].id == 0x123 && c.packets[2].dlc == 0);
        CHECK(c.parser.stats().checksumErrors >= 1);
        CHECK(c.parser.stats().lengthErrors == 3);
    }
}

static void test_roundtrip_all_lengths()
{
    std::vector<uint8_t> stream;
    for (uint8_t dlc = 0; dlc <= 8; dlc++)
    {
        std::vector<uint8_t> d;
        for (uint8_t i = 0; i < dlc; i++) d.push_back((uint8_t)(0x7F + i * 0x2B));
        append(stream, frame((uint16_t)(0x100 + dlc), d));
    }
    Collector c;
    c.feed(stream, 4);
    CHECK(c.packets.size() == 9);
    for (size_t i = 0; i < c.packets.size(); i++)
    {
        CHECK(c.packets[i].id == 0x100 + i);
        CHECK(c.packets[i].dlc == i);
    }
    CHECK(c.parser.stats().checksumErrors == 0 && c.parser.stats().discardedBytes == 0);
}

static void test_reset_drops_partial()
{
    std::vector<uint8_t> f = frame(0x221, {0, 1, 0, 1});
    Collector c;
    c.feed(std::vector<uint8_t>(f.begin(), f.begin() + 5));
    c.parser.reset();
    c.feed(f);
    CHECK(c.packets.size() == 1);
}

static void test_json()
{
    short vars[NUM_OF_VARS] = {0};
    vars[VAR_CONS_TODAY_10WH] = 123;
    vars[VAR_BMS1_CELL1_MV] = 3305;
    vars[VAR_LOAD_A100] = 250;

    cJSON* uha = cJSON_Parse(build_uha_json(vars, 1700000000).c_str());
    CHECK(uha != nullptr);
    CHECK(cJSON_GetNumberValue(cJSON_GetObjectItem(uha, "VAR_CONS_TODAY_WH")) == 1230);
    CHECK(cJSON_GetNumberValue(cJSON_GetObjectItem(uha, "VAR_BMS1_CELL1_MV")) == 3305);
    CHECK(cJSON_GetObjectItem(uha, "VAR_BMS3_CELL16_C") != nullptr);
    CHECK(cJSON_GetNumberValue(cJSON_GetObjectItem(uha, "UnixTime")) == 1700000000);
    cJSON_Delete(uha);

    cJSON* bms = cJSON_Parse(build_bms_json(vars, 1700000000).c_str());
    CHECK(bms != nullptr);
    cJSON* live = cJSON_GetObjectItem(bms, "LiveData");
    CHECK(live != nullptr);
    CHECK(cJSON_GetObjectItem(live, "TotalChargingKwh") == nullptr);
    CHECK(cJSON_GetObjectItem(live, "TotalDischargingKwh") == nullptr);
    CHECK(cJSON_GetNumberValue(cJSON_GetObjectItem(live, "DischargingA")) == 2.5);
    CHECK(cJSON_GetArraySize(cJSON_GetObjectItem(bms, "Cells")) == 16);
    CHECK(cJSON_GetNumberValue(cJSON_GetObjectItem(cJSON_GetArrayItem(cJSON_GetObjectItem(bms, "Cells"), 0), "VoltageV")) == 3.305);
    cJSON_Delete(bms);
}

static void test_event_line()
{
    struct tm lt = {};
    lt.tm_mday = 5; lt.tm_mon = 2; lt.tm_year = 126; lt.tm_hour = 7; lt.tm_min = 8; lt.tm_sec = 9;
    const uint8_t data[8] = {4, 0, 12, 0, 0, 0, 0, 255};
    CHECK(event_format_line(data, lt) == "05.03.2026 07:08:09 ELECON STARTUP 12 0 0 0 0 255\n");
    const uint8_t unknown[8] = {99, 9, 1, 2, 3, 4, 5, 6};
    CHECK(event_format_line(unknown, lt) == "05.03.2026 07:08:09 UNKNOWN UNKNOWN_EVENT 1 2 3 4 5 6\n");
}

int main()
{
    test_encode();
    test_single_and_split();
    test_start_byte_at_chunk_end();
    test_garbage_and_errors();
    test_roundtrip_all_lengths();
    test_reset_drops_partial();
    test_json();
    test_event_line();
    if (sFailures == 0) printf("All tests passed\n");
    return sFailures == 0 ? 0 : 1;
}

// Golden test: byte-compare uha.json / bms.json produced by the original UHA5 code
// (UHA/UHA5/UHA.cpp, paths patched by compare_with_v5.sh) with the UhaGate6 builders
// for many random variable sets. Built and run only by compare_with_v5.sh.
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <fstream>
#include <sstream>
#include <string>

#define private public
#include "UHA.h"   // UHA5 class, from UHA/UHA5
#undef private
#include "outputs.h"

extern "C" {
#include "rpiserp.h"   // UHA5 serial API, stubbed below
void RPISERP_Init(unsigned char*) {}
void RPISERP_Start(void) {}
void RPISERP_Stop(void) {}
void RPISERP_SendPacket(sPacket*) {}
int RPISERP_GetNumOfRxPackets(void) { return 0; }
int RPISERP_GetRxPacket(sPacket*) { return 0; }
}

static std::string slurp(const char* path)
{
    std::ifstream in(path, std::ios::binary);
    std::stringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

int main(int argc, char** argv)
{
    const int rounds = argc > 1 ? atoi(argv[1]) : 200;
    UHA uha;
    int compared = 0, failures = 0;
    srand(12345);
    for (int round = 0; round < rounds; round++)
    {
        for (int i = 0; i < NUM_OF_VARS; i++)
            uha.mVars[i] = (round == 0) ? 0 : (short)((rand() & 0xFFFF) - 32768);

        time_t before = time(nullptr);
        uha.UHA_CreateUhaJson();
        uha.UHA_CreateBmsJson();
        std::string v6uha = build_uha_json(uha.mVars, (int)before);
        std::string v6bms = build_bms_json(uha.mVars, (int)before);
        if (time(nullptr) != before) continue;   // second changed in between, UnixTime differs

        compared++;
        if (slurp("v5_uha.json") != v6uha)
        {
            printf("round %d: uha.json differs\n", round);
            failures++;
        }
        if (slurp("v5_bms.json") != v6bms)
        {
            printf("round %d: bms.json differs\n", round);
            failures++;
        }
    }
    printf("compared %d rounds, %d differences\n", compared, failures);
    return (failures == 0 && compared > rounds / 2) ? 0 : 1;
}

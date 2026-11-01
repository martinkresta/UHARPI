// Prints uha.json and bms.json made by the UhaGate6 C++ builders (UHA/UHA6/src/outputs.cpp)
// for a given set of old variable values. Used only by tests/test_golden_uhagate6.py.
//   golden_dump <values file> <unix time> <uha.json out> <bms.json out>
// values file: one "VAR_NAME value" per line.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>

#include "outputs.h"
#include "uha_vars.h"

struct VarName { int id; const char* name; };
static const VarName kVarNames[] = {
#include "var_names.inc"
};

int main(int argc, char** argv)
{
    if (argc != 5) { fprintf(stderr, "usage: golden_dump values time uha.json bms.json\n"); return 2; }
    short vars[NUM_OF_VARS] = {0};
    std::ifstream in(argv[1]);
    std::string name;
    int value;
    while (in >> name >> value)
    {
        bool found = false;
        for (const VarName& v : kVarNames)
            if (name == v.name) { vars[v.id] = (short)value; found = true; }
        if (!found) { fprintf(stderr, "unknown variable %s\n", name.c_str()); return 2; }
    }
    int time = atoi(argv[2]);
    std::ofstream(argv[3]) << build_uha_json(vars, time);
    std::ofstream(argv[4]) << build_bms_json(vars, time);
    return 0;
}

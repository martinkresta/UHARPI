// JSON outputs compatible with UhaGate5 (same keys, order, scaling and cJSON formatting).
#ifndef UHA6_OUTPUTS_H
#define UHA6_OUTPUTS_H

#include <string>

// Returned strings are the cJSON_Print() output (no trailing newline), empty on allocation failure.
std::string build_uha_json(const short* mVars, int Time);
std::string build_bms_json(const short* mVars, int Time);

#endif

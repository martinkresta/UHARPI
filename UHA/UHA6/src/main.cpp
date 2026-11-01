// UhaGate6 - Raspberry Pi gateway between the UHA CAN nodes (via ELECON serial link) and the web.
#include "config.h"
#include "gateway.h"
#include "log.h"

int main(int argc, char** argv)
{
    Config cfg;
    int rc = config_parse(argc, argv, cfg);
    if (rc >= 0) return rc;

    log_init(cfg.verbose);
    Gateway gateway(cfg);
    return gateway.run();
}

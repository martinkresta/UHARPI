#include "outputs.h"

#include "cJSON.h"
#include "uha_vars.h"

// Print and free the tree; UHA5 leaked the cJSON_Print() buffer every second.
static std::string print_and_delete(cJSON* root)
{
    std::string text;
    char* printed = cJSON_Print(root);
    if (printed != nullptr)
    {
        text = printed;
        cJSON_free(printed);
    }
    cJSON_Delete(root);
    return text;
}

std::string build_uha_json(const short* mVars, int Time)
{
    cJSON* Uha = cJSON_CreateObject();
#include "uha_json_body.inc"
    return print_and_delete(Uha);
}

// Same content as UHA5 UHA_CreateBmsJson(). The values (including the integer-division
// percentages and TodayDiffKwh in Wh) are kept as they are, so readers see no change.
std::string build_bms_json(const short* mVars, int Time)
{
    int SunPowerW = (int)(mVars[VAR_SOLAR_POWER_W]);
    int SunPowerPct = (int)(SunPowerW / 11200) * 100;
    int LoadPowerW = (int)(mVars[VAR_LOAD_W]);
    int LoadPowerPct = (int)(LoadPowerW / 8000) * 100;
    double TodayDiffKwh = (mVars[VAR_SOLAR_ENERGY_TODAY_10WH] * 10 - mVars[VAR_CONS_TODAY_10WH] * 10);   // WH!
    double totalCharging = (mVars[VAR_AXPERT_BAT_CHARGING_A] + (mVars[VAR_MPPT_BAT_CURRENT_A10] / 10.0));

    cJSON* Bms = cJSON_CreateObject();
    cJSON* PackInfo = cJSON_CreateObject();
    cJSON* LiveData = cJSON_CreateObject();
    cJSON* CellsJson = cJSON_CreateArray();

    cJSON_AddItemToObject(PackInfo, "CapacityKwh", cJSON_CreateNumber(16));
    cJSON_AddItemToObject(PackInfo, "MinCellVoltageV", cJSON_CreateNumber(3));
    cJSON_AddItemToObject(PackInfo, "MaxCellVoltageV", cJSON_CreateNumber(3.6));
    cJSON_AddItemToObject(PackInfo, "BalanceCellVoltageV", cJSON_CreateNumber(3.5));
    cJSON_AddItemToObject(PackInfo, "NumOfCells", cJSON_CreateNumber(16));
    cJSON_AddItemToObject(Bms, "BatteryPackInfo", PackInfo);

    // UHA5 also "added" a 2nd DischargingA, TotalChargingKwh and TotalDischargingKwh with a NULL
    // item; cJSON ignores NULL items, so those keys never appeared in bms.json and are omitted here.
    cJSON_AddItemToObject(LiveData, "SunPowerW", cJSON_CreateNumber(SunPowerW));
    cJSON_AddItemToObject(LiveData, "TotalVoltageV", cJSON_CreateNumber(mVars[VAR_BAT_VOLTAGE_V10] / 10.0));
    cJSON_AddItemToObject(LiveData, "ChargingA", cJSON_CreateNumber(totalCharging));
    cJSON_AddItemToObject(LiveData, "DischargingA", cJSON_CreateNumber(mVars[VAR_LOAD_A100] / 100.0));
    cJSON_AddItemToObject(LiveData, "TodayChargingKwh", cJSON_CreateNumber(mVars[VAR_SOLAR_ENERGY_TODAY_10WH] / 100.0));
    cJSON_AddItemToObject(LiveData, "TodayDischargingKwh", cJSON_CreateNumber(mVars[VAR_CONS_TODAY_10WH] / 100.0));
    cJSON_AddItemToObject(LiveData, "AvailableEnergyKwh", cJSON_CreateNumber(mVars[VAR_BAT_ENERGY_WH] / 1000.0));
    cJSON_AddItemToObject(LiveData, "SocPct", cJSON_CreateNumber(mVars[VAR_BAT_SOC]));
    cJSON_AddItemToObject(LiveData, "TemperatureC", cJSON_CreateNumber(mVars[VAR_BMS2_CELL4_C]));
    cJSON_AddItemToObject(LiveData, "SunPowerPct", cJSON_CreateNumber(SunPowerPct));
    cJSON_AddItemToObject(LiveData, "BattCurrentA", cJSON_CreateNumber(mVars[VAR_BAT_CURRENT_A10] / 10.0));
    cJSON_AddItemToObject(LiveData, "LoadCurrentA", cJSON_CreateNumber(mVars[VAR_LOAD_A100] / 100.0));
    cJSON_AddItemToObject(LiveData, "LoadPowerW", cJSON_CreateNumber(mVars[VAR_LOAD_W]));
    cJSON_AddItemToObject(LiveData, "LoadPowerPct", cJSON_CreateNumber(LoadPowerPct));
    cJSON_AddItemToObject(LiveData, "TodayDiffKwh", cJSON_CreateNumber(TodayDiffKwh));
    cJSON_AddItemToObject(LiveData, "UnixTime", cJSON_CreateNumber(Time));
    cJSON_AddItemToObject(Bms, "LiveData", LiveData);

    for (int i = 0; i < 16; i++)
    {
        cJSON* Cell = cJSON_CreateObject();
        cJSON_AddItemToObject(Cell, "VoltageV", cJSON_CreateNumber(mVars[i + VAR_BMS1_CELL1_MV] / 1000.0));
        cJSON_AddItemToObject(Cell, "TemperatureC", cJSON_CreateNumber(mVars[i + VAR_BMS1_CELL1_C]));
        cJSON_AddItemToArray(CellsJson, Cell);
    }
    cJSON_AddItemToObject(Bms, "Cells", CellsJson);

    return print_and_delete(Bms);
}

// uha.js
// Reads from uha.json (flat VAR_* variables produced by UHA_CreateUhaJson)
// bms.js / bms.json kept intact as fallback

var INTERVAL_MS = 3000;
var error_msg = $("#update-error");
var CellChart;
var selectedPack = 1; // 1=BMS1 workshop 251Ah, 2=BMS2 house 220Ah, 3=BMS3 house 80Ah
var lastResp = null;

// bright colors
var c_success = 'rgba(40, 167, 69, 1)';
var c_warning = 'rgba(255, 193, 7, 1)';
var c_danger  = 'rgba(220, 53, 69, 1)';

// transparent colors
var c_success_t = 'rgba(40, 167, 69, 0.3)';
var c_warning_t = 'rgba(255, 193, 7, 0.3)';
var c_danger_t  = 'rgba(220, 53, 69, 0.3)';


// Build a 16-element cell array from the flat VAR_BMSx_CELLy_MV/C keys
function getCells(resp, packNum) {
    var cells = [];
    for (var i = 1; i <= 16; i++) {
        var mvKey = "VAR_BMS" + packNum + "_CELL" + i + "_MV";
        var cKey  = "VAR_BMS" + packNum + "_CELL" + i + "_C";
        cells.push({
            VoltageV:     (resp[mvKey] || 0) / 1000.0,
            TemperatureC:  resp[cKey]  || 0
        });
    }
    return cells;
}


function update() {
    $.ajax({
        method:   'GET',
        dataType: 'json',
        url:      "./uha.json",
        success: function(resp) {
            error_msg.hide();
            lastResp = resp;
            UpdateDashboard(resp);
            UpdateCells(resp);
            DrawCellChart(getCells(resp, selectedPack));
        },
        error: function(xhr, status, error) {
            error_msg.show();
        }
    });
}


function UpdateDashboard(resp) {
    // -- Solar card --
    var SunPowerW       = resp["VAR_SOLAR_POWER_W"]            || 0;
    var SolarVoltageV   = (resp["VAR_MPPT_SOLAR_VOLTAGE_V100"] || 0) / 100.0;
    var ChargingA       = (resp["VAR_AXPERT_BAT_CHARGING_A"]   || 0)
                        + (resp["VAR_MPPT_BAT_CURRENT_A10"]    || 0) / 10.0;
    var SunPowerPct     = (SunPowerW / 11200) * 100;
    // VAR_SOLAR_ENERGY_TODAY_10WH: unit is 10Wh, so /100 = kWh
    var TodayChargingKwh = (resp["VAR_SOLAR_ENERGY_TODAY_10WH"] || 0) / 100.0;

    // -- Battery card --
    var SocPct            = resp["VAR_BAT_SOC"]           || 0;
    var BattVoltageV      = (resp["VAR_BAT_VOLTAGE_V10"]  || 0) / 10.0;
    var BattCurrentA      = (resp["VAR_BAT_CURRENT_A10"]  || 0) / 10.0;
    var AvailableEnergyKwh = (resp["VAR_BAT_ENERGY_WH"]   || 0) / 1000.0;
    // Diff today: (solar_10wh - cons_10wh) * 10 = Wh, /1000 = kWh
    var TodayDiffKwh = ((resp["VAR_SOLAR_ENERGY_TODAY_10WH"] || 0) * 10
                      - (resp["VAR_CONS_TODAY_10WH"]         || 0) * 10) / 1000.0;

    // -- Load card --
    var LoadPowerW         = resp["VAR_LOAD_W"]       || 0;
    var LoadCurrentA       = (resp["VAR_LOAD_A100"]   || 0) / 100.0;
    var TodayDischargingKwh = (resp["VAR_CONS_TODAY_10WH"] || 0) / 100.0;
    var LoadPowerPct       = (LoadPowerW / 8000) * 100;

    // -- Weather card --
    var TemperatureC = resp["VAR_BMS2_CELL4_C"] || 0;

    // -- Timestamp --
    var date = new Date((resp["UnixTime"] || 0) * 1000);

    // Solar
    $("#SunPowerW").html(SunPowerW.toFixed(0) + " W");
    $("#SunChargingA").html(ChargingA.toFixed(2) + " A");
    $("#SunPowerPct").html(SunPowerPct.toFixed(0) + " %");
    $("#SunVoltageV").html(SolarVoltageV.toFixed(1) + " V");
    $("#TodayChargingKwh").html(TodayChargingKwh.toFixed(3) + " kWh");

    // Battery
    $("#SocPct").html(SocPct.toFixed(0) + " %");
    $("#TodayDiffKwh").html(TodayDiffKwh.toFixed(3) + " kWh");
    $("#AvailableEnergyKwh").html(AvailableEnergyKwh.toFixed(2) + " kWh");
    $("#TotalVoltageV").html(BattVoltageV.toFixed(1) + " V");
    $("#BattCurrentA").html(BattCurrentA.toFixed(2) + " A");

    // Load
    $("#LoadPowerW").html(LoadPowerW.toFixed(0) + " W");
    $("#TodayDischargingKwh").html(TodayDischargingKwh.toFixed(3) + " kWh");
    $("#LoadPowerPct").html(LoadPowerPct.toFixed(0) + " %");
    $("#LoadVoltageV").html(BattVoltageV.toFixed(1) + " V");
    $("#DischargingA").html(LoadCurrentA.toFixed(2) + " A");

    // Weather
    $("#TemperatureC").html(TemperatureC.toFixed(0) + " °C");

    $(".LastUpdate").html("Last Update : " + FormatDateTime(date));
}


function FormatDateTime(JsDate) {
    var day     = JsDate.getDate();
    var month   = JsDate.getMonth() + 1;
    var year    = JsDate.getFullYear();
    var hours   = JsDate.getHours();
    var minutes = JsDate.getMinutes();
    var seconds = JsDate.getSeconds();
    if (minutes < 10) { minutes = '0' + minutes; }
    if (seconds < 10) { seconds = '0' + seconds; }
    if (!day) { return "unknown"; }
    return day + '.' + month + '.' + year + '  ' + hours + ':' + minutes + ':' + seconds;
}


function UpdateCells(resp) {
    var packs = [getCells(resp, 1), getCells(resp, 2), getCells(resp, 3)];

    $("#tablevoltages tbody").empty();
    $("#tabletemps tbody").empty();

    for (var j = 0; j < 16; j++) {
        var trV = $("<tr>");
        var trT = $("<tr>");
        trV.append($("<td>").html(j + 1));
        trT.append($("<td>").html(j + 1));
        for (var p = 0; p < 3; p++) {
            trV.append($("<td>").html(packs[p][j].VoltageV.toFixed(3)));
            trT.append($("<td>").html(packs[p][j].TemperatureC));
        }
        $("#tablevoltages tbody").append(trV);
        $("#tabletemps tbody").append(trT);
    }
}


function DrawCellChart(cells) {
    var labels = [], voltages = [];
    for (var j = 0; j < cells.length; j++) {
        labels.push(j + 1);
        voltages.push(cells[j].VoltageV.toFixed(3));
    }

    if (CellChart) { CellChart.destroy(); }

    var ctx = $("#CellsChart");
    CellChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Voltage',
                data: voltages,
                borderWidth: 1,
                borderColor: c_success,
                backgroundColor: function(context) {
                    var value = context.dataset.data[context.dataIndex];
                    if (value < 3.0 || value > 3.6) { return c_danger_t; }
                    if (value > 3.499)               { return c_warning_t; }
                    return c_success_t;
                }
            }]
        },
        options: {
            animation: false,
            legend: { display: false },
            scales: {
                yAxes: [{ ticks: { min: 2.8, max: 3.7 } }]
            }
        }
    });
}


$(document).ready(function() {

    // Inject pack selector tabs into the chart card header
    $('#CellsChart').closest('.card').find('.card-header').append(
        '<ul class="nav nav-tabs mt-2" id="packTabs">' +
        '<li class="nav-item"><a class="nav-link active" href="#" data-pack="1">BMS 1 &mdash; Workshop 251 Ah</a></li>' +
        '<li class="nav-item"><a class="nav-link" href="#" data-pack="2">BMS 2 &mdash; House 220 Ah</a></li>' +
        '<li class="nav-item"><a class="nav-link" href="#" data-pack="3">BMS 3 &mdash; House 80 Ah</a></li>' +
        '</ul>'
    );

    $('#packTabs').on('click', 'a', function(e) {
        e.preventDefault();
        $('#packTabs a').removeClass('active');
        $(this).addClass('active');
        selectedPack = parseInt($(this).data('pack'));
        if (lastResp) {
            DrawCellChart(getCells(lastResp, selectedPack));
        }
    });

    // collapse sidebar on mobile
    if ($(window).width() < 767) {
        $("body").toggleClass("sidebar-toggled");
        $(".sidebar").toggleClass("toggled");
    }

    update();
    setInterval(function() { update(); }, INTERVAL_MS);
});

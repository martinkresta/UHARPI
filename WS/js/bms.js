// JavaScript Document
// bms.js


var INTERVAL_MS = 3000; // 3 sec
var error_msg = $("#update-error");
var CellChart;

// bright colors
var c_success ='rgba(40, 167, 69, 1)';
var c_warning = 'rgba(255, 193, 7, 1)';
var c_danger = 'rgba(220, 53, 69, 1)';


// transparent colors
var c_success_t ='rgba(40, 167, 69, 0.3)';
var c_warning_t = 'rgba(255, 193, 7, 0.3)';
var c_danger_t = 'rgba(220, 53, 69, 0.3)';


function update() {

	$.ajax({
		method: 'GET',
		dataType: 'json',
		url: "./bms.json",
		success: function(resp) {
			error_msg.hide();
			UpddateDashboard(resp);
			UpdateCells(resp);
			DrawCellChart(resp);
		/*	if (!CellChart)
			{
				DrawCellChart(resp);
			}
			else
			{
				UpdateCellChart(resp);
			} */
		},                                     
		error:  function(xhr, status, error) {
			$('#power').text("777");
			$('#power').text(JSON.parse(xhr.responseText).error);
			alertify.error(JSON.parse(xhr.responseText).error);
		},
	}); 	
}


// update dashboard - live data
function UpddateDashboard(resp) {
	var blocks = ["BatteryPackInfo", "LiveData"];
	var block = resp[blocks[1]];
	var BattCurrentA = (block["ChargingA"] - block["DischargingA"]);
	var LoadPowerW = (block["DischargingA"]*block["TotalVoltageV"]);
	var SunPowerPct = (block["SunPowerW"] / 1100) * 100;
	var LoadPowerPct = (LoadPowerW / 3000) * 100;
	var TodayDiffKwh = (block["TodayChargingKwh"] - block["TodayDischargingKwh"]);
	var date = new Date(block["UnixTime"]*1000); // *1000 because of date takes milliseconds
	
	$("#SunPowerW").html(block["SunPowerW"].toFixed(0) + " W");
	$("#SunChargingA").html(block["ChargingA"].toFixed(1) + " A");
	$("#SunPowerPct").html(SunPowerPct.toFixed(0) + " %");
	$("#TodayChargingKwh").html(block["TodayChargingKwh"].toFixed(3) + " kWh");


	$("#SocPct").html(block["SocPct"].toFixed(0) + " %");
	$("#TodayDiffKwh").html(TodayDiffKwh.toFixed(3) + " kWh");
	$("#AvailableEnergyKwh").html(block["AvailableEnergyKwh"].toFixed(2) + " kWh");
	$("#TotalVoltageV").html(block["TotalVoltageV"].toFixed(1) + " V");
	$("#BattCurrentA").html(BattCurrentA.toFixed(1) + " A");
	

	$("#LoadPowerW").html(LoadPowerW.toFixed(0) + " W");
	$("#TodayDischargingKwh").html(block["TodayDischargingKwh"].toFixed(3) + " kWh");
	$("#LoadPowerPct").html(LoadPowerPct.toFixed(0) + " %");
	$("#LoadVoltageV").html(block["TotalVoltageV"].toFixed(1) + " V");
	$("#DischargingA").html(block["DischargingA"].toFixed(1) + " A");
	
	
	$("#TemperatureC").html(block["TemperatureC"].toFixed(0) + " °C");

	$(".LastUpdate").html("Last Update : " + FormatDateTime(date));

}

// formatting of date time 
function FormatDateTime (JsDate) {
	//var day = (date.getDate() < 10 ? '0' : '') + date.getDate();
	// var month = (date.getMonth() < 9 ? '0' : '') + (date.getMonth() + 1);
	var day = JsDate.getDate();
	var month = JsDate.getMonth() + 1;
	var year = JsDate.getFullYear();
	
	var hours = JsDate.getHours();
	var minutes = JsDate.getMinutes();
	var seconds = JsDate.getSeconds();
  if (minutes < 10)
  {
    minutes = '0' + minutes;
  }
  if (seconds < 10)
  {
    seconds = '0' + seconds;
  } 
  
	if (!day)
	{
		var datetimestring = "unknown"
	}
	else
	{
		var datetimestring = day + '.' + month + '.' + year + '  ' + hours + ':' + minutes + ':' + seconds;
	}
	return datetimestring;
}


// array to table
function UpdateCells(resp) {
	var blocks = ["Cells"];
	var row; 
	for (var i = 0; i < blocks.length; i++) {
		var block = resp[blocks[i]];
		$("#tablecells").children("tr").remove(); // remove old data

		for (var j = 0; j < block.length; j++) {
			var tr = $("<tr>");
			tr.append($("<td>").html((j + 1)));
			var cellVoltage = block[j]["VoltageV"];
			var cellTemp = block[j]["TemperatureC"];
			tr.append($("<td>").html(cellVoltage.toFixed(3)));
			tr.append($("<td>").html(cellTemp));
			$("#tablecells").append(tr);// insert			
		}
	}
}


function DrawCellChart(resp)
{
	var labels = [], voltages=[];

	var block = resp["Cells"];
	for (var j = 0; j < block.length; j++) {
		var cellVoltage = block[j]["VoltageV"];
		var cellTemp = block[j]["TemperatureC"];
		labels.push(parseInt(j+1));
		voltages.push(cellVoltage.toFixed(3));
	}

	var ctx = $("#CellsChart");
	CellChart = new Chart(ctx, {
		type: 'bar',
		data: {
			labels: labels,
			datasets: [{
				label: 'Voltage',
				data: voltages,
				borderWidth: 1,
				borderColor: 'rgba(40, 167, 69, 1)',
				 function(context) {
					var index = context.dataIndex;
					var value = context.dataset.data[index];
					if(value < 3.0 || value > 3.6)
					{
						return c_danger;
					}
					else if (value > 3.499 && value < 3.6)
					{
						return c_warning;
					}
					else
					{
						return c_success;
					}
				}, 
				backgroundColor: function(context) {
					var index = context.dataIndex;
					var value = context.dataset.data[index];
					if(value < 3.0 || value > 3.6)
					{
						return c_danger_t;
					}
					else if (value > 3.499 && value < 3.6)
					{
						return c_warning_t;
					}
					else
					{
						return c_success_t;
					}
				}  
			}]
		},
		options: {
			animation: false,
			legend: {
				display: false
			},
			scales: {
				yAxes: [{
					ticks: {
						min: 2.8,
						max: 3.7
					}
				}]
			}
		}
	});

}

function UpdateCellChart(resp)
{
	var  voltages=[];

	var block = resp["Cells"];
	for (var j = 0; j < block.length; j++) {
		var cellVoltage = block[j]["VoltageV"];
		voltages.push(cellVoltage.toFixed(3));
	}

	CellChart.data.dataset[0].push(voltages);
	CellChart.update();
}


// after document is loaded
$(document).ready(function() {
	
	

	if ($(window).width() < 767) 
	{
		$("body").toggleClass("sidebar-toggled");
		$(".sidebar").toggleClass("toggled");
//		e.preventDefault();
	}

	update(); // download data now
	
	setInterval(function() { // download data timer
		update(); // download data now
	}, INTERVAL_MS);
});

 
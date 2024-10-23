#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# AC Aircon Smart Remote plugin using CASA.IA CAC 221 for Domoticz
# Author: MrErwan,
# Version:    0.0.1: alpha..

"""
<plugin key="METEO-FR" name="Meteo plugin from Ronelabs" author="Erwanweb" version="0.0.2" externallink="https://github.com/Erwanweb/Meteo-fr.git">
      <description>
        <h2>Meteo plugin from Ronelabs</h2><br/>
        Easily implement in Domoticz Meteo datas<br/>
        <h3>Set-up and Configuration</h3>
    </description>
    <params>
        <param field="Password" label="API Key" width="300px" required="true" default=""/>
        <param field="Mode1" label="Lat." width="150px" required="true" default=""/>
        <param field="Mode2" label="Long." width="150px" required="true" default=""/>
        <param field="Mode6" label="Logging Level" width="200px">
            <options>
                <option label="Normal" value="Normal"  default="true"/>
                <option label="Verbose" value="Verbose"/>
                <option label="Debug - Python Only" value="2"/>
                <option label="Debug - Basic" value="62"/>
                <option label="Debug - Basic+Messages" value="126"/>
                <option label="Debug - Connections Only" value="16"/>
                <option label="Debug - Connections+Queue" value="144"/>
                <option label="Debug - All" value="-1"/>
            </options>
        </param>
    </params>
</plugin>
"""
import Domoticz
import json
import urllib.parse as parse
import urllib.request as request
from datetime import datetime, timedelta
import time
import math
import base64
import itertools
import requests

try:
    from Domoticz import Devices, Images, Parameters, Settings
except ImportError:
    pass

class deviceparam:

    def __init__(self, unit, nvalue, svalue):
        self.unit = unit
        self.nvalue = nvalue
        self.svalue = svalue


class BasePlugin:

    def __init__(self):

        self.debug = False
        self.OutTemp = 20.0
        self.OutHum = 50
        self.FeelTemp = 20.0
        self.TodayMinTemp = 20.0
        self.TodayMaxTemp = 20.0
        self.MeteoRequest = datetime.now()
        self.dju0 = 0
        self.dju1 = 0
        return


    def onStart(self):

        # setup the appropriate logging level
        try:
            debuglevel = int(Parameters["Mode6"])
        except ValueError:
            debuglevel = 0
            self.loglevel = Parameters["Mode6"]
        if debuglevel != 0:
            self.debug = True
            Domoticz.Debugging(debuglevel)
            DumpConfigToLog()
            self.loglevel = "Verbose"
        else:
            self.debug = False
            Domoticz.Debugging(0)

        # create the child devices if these do not exist yet
        devicecreated = []
        if 1 not in Devices:
            Domoticz.Device(Name="Actual Temp", Unit=1, TypeName="Temp+Hum", Used=1).Create()
            devicecreated.append(deviceparam(1, 0, "20;50;1"))  # default is 20 degrees 50% normal
        if 2 not in Devices:
            Domoticz.Device(Name="Feel Temp", Unit=2, TypeName="Temperature", Used=1).Create()
            devicecreated.append(deviceparam(2, 0, "20"))  # default is 20 degrees
        if 3 not in Devices:
            Domoticz.Device(Name="TempHumBaro", Unit=3, TypeName="Temp+Hum+Baro", Used=1).Create()
            devicecreated.append(deviceparam(3, 0, "20;50;0;1020;0"))  # default is 20;50;0;1020;0
        if 4 not in Devices:
            Domoticz.Device(Name="Wind", Unit=4, TypeName="Wind", Used=1).Create()
            devicecreated.append(deviceparam(4, 0, "90;N;16;25;20;20"))  # default is 90,N,16,25,20º,21º
        if 5 not in Devices:
            Domoticz.Device(Name="Today THB", Unit=5, TypeName="Temp+Hum+Baro", Used=1).Create()
            devicecreated.append(deviceparam(5, 0, "21;60;0;1018;2"))  # default is 20;50;0;1020;0
        if 6 not in Devices:
            Domoticz.Device(Name="Today Min.Temp", Unit=6, TypeName="Temperature", Used=1).Create()
            devicecreated.append(deviceparam(6, 0, "20"))  # default is 20 degrees
        if 7 not in Devices:
            Domoticz.Device(Name="Today Max.Temp", Unit=7, TypeName="Temperature", Used=1).Create()
            devicecreated.append(deviceparam(7, 0, "20"))  # default is 20 degrees
        if 8 not in Devices:
            Domoticz.Device(Name="DJU-Prev", Unit=8, TypeName="Custom", Used=1).Create()
            devicecreated.append(deviceparam(8, 0, "0"))  # default is zero DJU


        # if any device has been created in onStart(), now is time to update its defaults
        for device in devicecreated:
            Devices[device.unit].Update(nValue=device.nvalue, sValue=device.svalue)

        # Set domoticz heartbeat to 20 s (onheattbeat() will be called every 20 )
        Domoticz.Heartbeat(20)

    def onStop(self):

        Domoticz.Debugging(0)


    def onCommand(self, Unit, Command, Level, Color):

        Domoticz.Debug("onCommand called for Unit {}: Command '{}', Level: {}".format(Unit, Command, Level))

    def onHeartbeat(self):

        Domoticz.Debug("onHeartbeat Called...")

        now = datetime.now()

        if self.MeteoRequest <= now:
            #WeatherMapAPI("")
            self.MeteoRequest = datetime.now() + timedelta(minutes=1) # make make an API Call every 30 minutes, to have max 50 per days

            jsonData = WeatherMapAPI("")
            if jsonData:
                # on recup les datas
                self.OutTemp = round(float(jsonData['current']['temp']), 1)
                Domoticz.Debug("Current outdoor temp = {}".format(self.OutTemp))
                self.OutHum = int(jsonData['current']['humidity'])
                Domoticz.Debug("Current outdoor hum = {}".format(self.OutHum))
                self.FeelTemp = round(float(jsonData['current']['feels_like']), 1)
                Domoticz.Debug("Current feel temp = {}".format(self.FeelTemp))
                self.TodayMinTemp = round(float(jsonData['daily'][0]['temp']['min']), 1)
                self.TodayMaxTemp = round(float(jsonData['daily'][0]['temp']['max']), 1)
                Domoticz.Debug("Current Min Temp = {} and Max = {}".format(self.TodayMinTemp, self.TodayMaxTemp))


                # Updating devices values
                Domoticz.Debug("Updating Devices from meteo datas")
                #Devices[1].Update(nValue= 0, sValue=str(self.OutTemp))
                Devices[1].Update(nValue= 0, sValue="{};{};1".format(str(self.OutTemp), str(self.OutHum)))
                Devices[2].Update(nValue= 0, sValue=str(self.FeelTemp))
                Devices[6].Update(nValue= 0, sValue=str(self.TodayMinTemp))
                Devices[7].Update(nValue= 0, sValue=str(self.TodayMaxTemp))
                # DJUs
                self.dju0 = (18-((self.TodayMinTemp + self.TodayMaxTemp)/2))
                self.dju0 = round(self.dju0, 1)
                if self.dju0 <= 0 :
                    self.dju0 = 0
                #self.dju0 = round( 18 - ((self.TodayMinTemp + self.TodayMaxTemp) / 2))), 1)
                Domoticz.Debug("DJU Prev. = {}".format(self.dju0))
                Devices[8].Update(nValue=0, sValue=str(self.dju0))

global _plugin
_plugin = BasePlugin()


def onStart():
    global _plugin
    _plugin.onStart()


def onStop():
    global _plugin
    _plugin.onStop()


def onCommand(Unit, Command, Level, Color):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Color)


def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()


# Plugin utility functions ---------------------------------------------------

def parseCSV(strCSV):
    listvals = []
    for value in strCSV.split(","):
        try:
            val = int(value)
            listvals.append(val)
        except ValueError:
            try:
                val = float(value)
                listvals.append(val)
            except ValueError:
                Domoticz.Error(f"Skipping non-numeric value: {value}")
    return listvals

def WeatherMapAPI(APICall):

    Domoticz.Debug("OpenWeatherMap API Called...")
    jsonData = None
    url = "https://api.openweathermap.org/data/3.0/onecall?appid={}&lat={}&lon={}&units=metric&lang=fr&exclude=minutely,hourly{}".format(Parameters["Password"], Parameters["Mode1"], Parameters["Mode2"], parse.quote(APICall, safe="&="))
    # ex : "https://api.openweathermap.org/data/3.0/onecall?appid=6b5f1c46010c3b99daba4f3ba529cfc4&lat=41.57387&lon=2.48982&units=metric&lang=fr&exclude=minutely,hourly"
    Domoticz.Debug("Calling OpenWeatherMap API: {}".format(url))
    try:
        req = request.Request(url)
        response = request.urlopen(req)
        if response.status == 200:
            jsonData = json.loads(response.read().decode('utf-8'))
        else:
            Domoticz.Error("OpenWeatherMap API: http error = {}".format(response.status))
    except:
        Domoticz.Error("Error calling '{}'".format(url))
    return jsonData


def CheckParam(name, value, default):

    try:
        param = int(value)
    except ValueError:
        param = default
        Domoticz.Error("Parameter '{}' has an invalid value of '{}' ! defaut of '{}' is instead used.".format(name, value, default))
    return param


# Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug("'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return
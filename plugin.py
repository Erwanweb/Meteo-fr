#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# AC Aircon Smart Remote plugin using CASA.IA CAC 221 for Domoticz
# Author: MrErwan,
# Version:    0.0.1: alpha..

"""
<plugin key="METEO-FR" name="Meteo plugin from Ronelabs" author="Ronelabs" version="0.0.2" externallink="https://github.com/Erwanweb/Meteo-fr.git">
      <description>
        <h2>Meteo plugin from Ronelabs</h2><br/>
        Easily implement in Domoticz Meteo datas<br/>
        <h3>Set-up and Configuration</h3>
    </description>
    <params>
        <param field="Password" label="API Key" width="300px" required="true" default=""/>
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
        self.lat = "0"
        self.lon = "0"
        self.MeteoRequest = datetime.now()
        self.APIK = "0"
        self.OutTemp = 20.0
        self.OutHum = 50
        self.FeelTemp = 20.0
        self.THBHumStat = 0
        self.THBBar = 1020
        self.THBBarStat = 0
        self.UV = 0
        # default is 90,N,16,25,20º,21º
        self.WindDeg = 0
        self.WindDir = "N"
        self.WindWS = 0 #*10 wind speed
        self.WindWg = 0  # *10 wind Gust
        self.THB0Temp = 20.0
        self.THB0Hum = 20.0
        self.THB0HumStat = 0
        self.THB0Bar = 1020
        self.THB0BarStat = 0
        self.TodayMinTemp = 20.0
        self.TodayMaxTemp = 20.0
        self.dju0 = 0
        self.dju1 = 0
        self.BarStat = 0
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
            Domoticz.Device(Name="Temp", Unit=1, TypeName="Temp+Hum", Used=1).Create()
            devicecreated.append(deviceparam(1, 0, "20;50;1"))  # default is 20 degrees 50% normal
        if 2 not in Devices:
            Domoticz.Device(Name="Feel Temp", Unit=2, TypeName="Temperature", Used=1).Create()
            devicecreated.append(deviceparam(2, 0, "20"))  # default is 20 degrees
        if 3 not in Devices:
            Domoticz.Device(Name="THB", Unit=3, Type=84, Subtype=16, Used=1).Create()
            devicecreated.append(deviceparam(3, 0, "20;50;0;1020;0"))  # default is 20;50;0;1020;0
        if 4 not in Devices:
            Domoticz.Device(Name="Wind", Unit=4, TypeName="Wind", Used=1).Create()
            devicecreated.append(deviceparam(4, 0, "90;N;16;25;20;20"))  # default is 90,N,16,25,20º,21º
        if 5 not in Devices:
            Domoticz.Device(Name="UV", Unit=5, TypeName="UV", Used=1).Create()
            devicecreated.append(deviceparam(5, 0, "0;0"))  # default is 0
        if 6 not in Devices:
            Domoticz.Device(Name="THB-Today", Unit=6, Type=84, Subtype=16, Used=1).Create()
            devicecreated.append(deviceparam(6, 0, "21;60;0;1018;2"))  # default is 20;50;0;1020;0
        if 7 not in Devices:
            Domoticz.Device(Name="Min.Temp-Today", Unit=7, TypeName="Temperature", Used=1).Create()
            devicecreated.append(deviceparam(7, 0, "20"))  # default is 20 degrees
        if 8 not in Devices:
            Domoticz.Device(Name="Max.Temp-Today", Unit=8, TypeName="Temperature", Used=1).Create()
            devicecreated.append(deviceparam(8, 0, "20"))  # default is 20 degrees
        if 9 not in Devices:
            Domoticz.Device(Name="DJU-Prev", Unit=9, TypeName="Custom", Used=1).Create()
            devicecreated.append(deviceparam(9, 0, "0"))  # default is zero DJU


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

        #if lat = 0 :
        if self.MeteoRequest <= now:
            self.MeteoRequest = datetime.now() + timedelta(minutes=1)  # make make an API Call every 30 minutes, to have max 50 per days
            Domoticz.Log("updating meteo datas")
            
            # Set location using domoticz param
            latlon = DomoticzAPI("type=command&param=getsettings")
            if latlon:
                self.lat = str(latlon['Location']['Latitude'])
                self.lon = str(latlon['Location']['Longitude'])
                Domoticz.Debug("Setting lat {} at and lon at {}".format(str(self.lat), str(self.lon)))

            # we check API Key
            Domoticz.Debug("Checking API Key")
            self.APIK = "0"
            # Nom du fichier à lire pour recuperer la cle
            key_file = "/home/tools/onevar/api_meteo.txt"

            # Lecture et stockage de la cle
            MeteoKey = read_txt_file(key_file)
            self.APIK = str(MeteoKey)
            Domoticz.Debug("API Key is  = {}".format(str(self.APIK)))

            #WeatherMapAPI("")
            jsonData = WeatherMapAPI("&lat={}&lon={}".format(str(self.lat), str(self.lon)))
            if jsonData:
                # on recup les datas
                self.OutTemp = round(float(jsonData['current']['temp']), 1)
                self.OutHum = int(jsonData['current']['humidity'])
                if self.OutHum <= 30 :
                    self.THBHumStat = 2
                elif self.OutHum >= 70 :
                    self.THBHumStat = 3
                else :
                    self.THBHumStat = 0
                self.THBBar = int(jsonData['current']['pressure'])
                self.THBBarStat = int(jsonData['current']['weather'][0]['id'])
                self.BarStat = self.THBBarStat
                self.BarStatLevel()
                self.THBBarStat = self.BarStat
                self.FeelTemp = round(float(jsonData['current']['feels_like']), 1)
                self.UV = round(float(jsonData['current']['uvi']), 1)
                self.WindDeg = round(float(jsonData['current']['wind_deg']), 1)
                self.WindDir = "N"
                self.WindWS = round(float((jsonData['current']['wind_speed'])*10), 1)
                self.WindWg = round(float((jsonData['daily'][0]['wind_gust'])*10), 1)
                self.THB0Temp = round(float(jsonData['daily'][0]['temp']['day']), 1)
                self.THB0Hum = int(jsonData['daily'][0]['humidity'])
                if self.THB0Hum <= 30 :
                    self.THB0HumStat = 2
                elif self.THB0Hum >= 70 :
                    self.THB0HumStat = 3
                else :
                    self.THB0HumStat = 0
                self.THB0Bar = int(jsonData['daily'][0]['pressure'])
                self.THB0BarStat = int(jsonData['daily'][0]['weather'][0]['id'])
                self.BarStat = self.THB0BarStat
                self.BarStatLevel()
                self.THB0BarStat = self.BarStat
                self.TodayMinTemp = round(float(jsonData['daily'][0]['temp']['min']), 1)
                self.TodayMaxTemp = round(float(jsonData['daily'][0]['temp']['max']), 1)

                # Updating devices values
                Domoticz.Debug("Updating Devices from meteo datas")
                #Devices[1].Update(nValue= 0, sValue=str(self.OutTemp))
                Devices[1].Update(nValue= 0, sValue="{};{};{}".format(str(self.OutTemp), str(self.OutHum), str(self.THBHumStat)))
                Devices[2].Update(nValue= 0, sValue=str(self.FeelTemp))
                Devices[3].Update(nValue= 0, sValue="{};{};{};{};{}".format(str(self.OutTemp), str(self.OutHum), str(self.THBHumStat), str(self.THBBar), str(self.THBBarStat)))
                # default is 90,N,16,25,20º,21º
                Devices[4].Update(nValue=0, sValue="{};{};{};{};{};{}".format(str(self.WindDeg), self.WindDir, str(self.WindWS), str(self.WindWg), str(self.OutTemp), str(self.FeelTemp)))
                Devices[5].Update(nValue= 0, sValue="{};0".format(str(self.UV)))
                Devices[6].Update(nValue=0, sValue="{};{};{};{};{}".format(str(self.THB0Temp), str(self.THB0Hum),str(self.THB0HumStat), str(self.THB0Bar),str(self.THB0BarStat)))
                Devices[7].Update(nValue= 0, sValue=str(self.TodayMinTemp))
                Devices[8].Update(nValue= 0, sValue=str(self.TodayMaxTemp))
                # DJUs
                self.dju0 = (18-((self.TodayMinTemp + self.TodayMaxTemp)/2))
                self.dju0 = round(self.dju0, 1)
                if self.dju0 <= 0 :
                    self.dju0 = 0
                Domoticz.Debug("DJU Prev. = {}".format(self.dju0))
                Devices[9].Update(nValue=0, sValue=str(self.dju0))

    def BarStatLevel(self):

        # Forecast: 0 = Heavy Snow, 1 = Snow, 2 = Heavy Rain, 3 = Rain, 4 = Cloudy, 5 = Some Clouds, 6 = Sunny, 7 = Unknown, 8 = Unstable, 9 = Stable

        if self.BarStat == 800:
            self.BarStat = 6
        elif self.BarStat > 800:
            if self.BarStat == 801:
                self.BarStat = 5
            elif self.BarStat == 802:
                self.BarStat = 5
            elif self.BarStat >= 803:
                self.BarStat = 4
        else:
            if self.BarStat < 500:
                self.BarStat = 2
            elif self.BarStat < 600:
                self.BarStat = 3
            elif self.BarStat < 700:
                self.BarStat = 1
            else:
                self.BarStat = 7

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

def DomoticzAPI(APICall):
    resultJson = None
    url = f"http://127.0.0.1:8080/json.htm?{parse.quote(APICall, safe='&=')}"

    try:
        Domoticz.Debug(f"Domoticz API request: {url}")
        req = request.Request(url)
        response = request.urlopen(req)

        if response.status == 200:
            resultJson = json.loads(response.read().decode('utf-8'))
            if resultJson.get("status") != "OK":
                Domoticz.Error(f"Domoticz API returned an error: status = {resultJson.get('status')}")
                resultJson = None
        else:
            Domoticz.Error(f"Domoticz API: HTTP error = {response.status}")

    except urllib.error.HTTPError as e:
        Domoticz.Error(f"HTTP error calling '{url}': {e}")

    except urllib.error.URLError as e:
        Domoticz.Error(f"URL error calling '{url}': {e}")

    except json.JSONDecodeError as e:
        Domoticz.Error(f"JSON decoding error: {e}")

    except Exception as e:
        Domoticz.Error(f"Error calling '{url}': {e}")

    return resultJson

def read_txt_file(key_file):
    try:
        with open(key_file, 'r', encoding='utf-8') as fichier:
            contenu = fichier.read()
        return contenu
    except FileNotFoundError:
        Domoticz.Error(f"Le fichier n'a pas été trouvé")
        return
    except IOError:
        Domoticz.Error(f"Une erreur s'est produite en essayant de lire le fichier.")
        return

    # Nom du fichier à lire pour recuperer la cle
    #key_file = "/home/tools/onevar/api_meteo.txt"

    # Lecture et stockage de la cle
    #contenu_fichier = read_txt_file(key_file)

def WeatherMapAPI(APICall):

    Domoticz.Debug("OpenWeatherMap API Called...")
    jsonData = None
    url = "https://api.openweathermap.org/data/3.0/onecall?appid={}&units=metric&lang=fr&exclude=minutely,hourly{}".format(Parameters["Password"], parse.quote(APICall, safe="&="))
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
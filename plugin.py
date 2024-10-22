"""
Meteo plugin for Domoticz using weathermap for French metro aera
Author: Erwanweb,
Version:    0.0.1: alpha
            0.0.2: beta
"""
"""
<plugin key="METEO-FR" name="Meteo plugin from Ronelabs" author="Erwanweb" version="0.0.2" externallink="https://github.com/Erwanweb/Meteo-fr.git">
    <description>
        <h2>Meteo plugin from Ronelabs</h2><br/>
        <h3>Set-up and Configuration</h3>
    </description>
    <params>
        <param field="Password" label="API Key" width="200px" required="true" default=""/>
        <param field="Mode1" label="Lat." width="100px" required="true" default=""/>
        <param field="Mode2" label="Long." width="100px" required="true" default=""/>
        <param field="Mode3" label="Opt. Outside Temp. Sensors (csv list of idx)" width="200px" required="false" default=""/>
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
import base64
import itertools
import requests

class deviceparam:

    def __init__(self, unit, nvalue, svalue):
        self.unit = unit
        self.nvalue = nvalue
        self.svalue = svalue


class BasePlugin:

    def __init__(self):

        self.debug = False
        self.OutTempSensors = []
        self.OutTemp = 20.0
        self.FeelTemp = 20.0
        self.TodayMinTemp = 20.0
        self.TodayMaxTemp = 20.0
        self.MeteoRequest = datetime.now()
        self.nexttemps = datetime.now()
        self.temptimeout = datetime.now()
        self.dju0 = 0
        self.dju1 = 0
        self.learn = True
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
            Domoticz.Device(Name="Actual Temp", Unit=1, TypeName="Temperature").Create()
            devicecreated.append(deviceparam(1, 0, "20"))  # default is 20 degrees
        if 2 not in Devices:
            Domoticz.Device(Name="Feel Temp", Unit=2, TypeName="Temperature").Create()
            devicecreated.append(deviceparam(2, 0, "20"))  # default is 20 degrees
        if 3 not in Devices:
            Domoticz.Device(Name="Today Min. Temp", Unit=3, TypeName="Temperature").Create()
            devicecreated.append(deviceparam(3, 0, "20"))  # default is 20 degrees
        if 4 not in Devices:
            Domoticz.Device(Name="Today Max. Temp", Unit=4, TypeName="Temperature").Create()
            devicecreated.append(deviceparam(4, 0, "20"))  # default is 20 degrees


        # if any device has been created in onStart(), now is time to update its defaults
        for device in devicecreated:
            Devices[device.unit].Update(nValue=device.nvalue, sValue=device.svalue)

        # build lists of sensors and switches
        self.OutTempSensors = parseCSV(Parameters["Mode3"])
        Domoticz.Debug("Outside Temperature sensors = {}".format(self.OutTempSensors))

        # build dict of status of all temp sensors to be used when handling timeouts
        for sensor in itertools.chain(self.OutTempSensors):
            self.ActiveSensors[sensor] = True

        # Set domoticz heartbeat to 20 s (onheattbeat() will be called every 20 )
        Domoticz.Heartbeat(20)

    def onStop(self):

        Domoticz.Debugging(0)


    def onCommand(self, Unit, Command, Level, Color):

        Domoticz.Debug("onCommand called for Unit {}: Command '{}', Level: {}".format(Unit, Command, Level))

    def onHeartbeat(self):

        now = datetime.now()

        if self.MeteoRequest <= now:
            WeatherMapAPI()
            self.MeteoRequest = datetime.now() + timedelta(minutes=2) # make make an API Call every 30 minutes, to have max 50 per days

        #if self.nexttemps <= now:
            # call the Domoticz json API for a temperature devices update, to get the lastest temps (and avoid the
            # connection time out time after 10mins that floods domoticz logs in versions of domoticz since spring 2018)
            #self.readTemps()

        # Updating devices values
        Domoticz.Debug("Updating Devices from Flipr Values")
        Devices[1].Update(nValue= 0, sValue=str(self.OutTemp))
        Devices[2].Update(nValue= 0, sValue=str(self.FeelTemp)
        Devices[3].Update(nValue= 0, sValue=str(self.TodayMinTemp)
        Devices[4].Update(nValue= 0, sValue=str(self.TodayMaxTemp)

    def readTemps(self):

        # set update flag for next temp update
        self.nexttemps = datetime.now() + timedelta(minutes=5)
        now = datetime.now()

        # fetch all the devices from the API and scan for sensors
        noerror = True
        listouttemps = []
        devicesAPI = DomoticzAPI("type=command&param=getdevices&filter=temp&used=true&order=Name")
        if devicesAPI:
            for device in devicesAPI["result"]:  # parse the devices for temperature sensors
                idx = int(device["idx"])
                if idx in self.OutTempSensors:
                    if "Temp" in device:
                        Domoticz.Debug("device: {}-{} = {}".format(device["idx"], device["Name"], device["Temp"]))
                        # check temp sensor is not timed out
                        if not self.SensorTimedOut(idx, device["Name"], device["LastUpdate"]):
                            listintemps.append(device["Temp"])
                    else:
                        Domoticz.Error("device: {}-{} is not a Temperature sensor".format(device["idx"], device["Name"]))

        # calculate the average outside temperature
        nbtemps = len(listouttemps)
        if nbtemps > 0:
            self.outtemp = round(sum(listouttemps) / nbtemps, 1)
        else:
            Domoticz.Debug("No Outside Temperature found...")
            self.outtemp = None

        self.WriteLog("Outside Temperature = {}".format(self.outtemp), "Verbose")
        return noerror

    def WriteLog(self, message, level="Normal"):

        if self.loglevel == "Verbose" and level == "Verbose":
            Domoticz.Log(message)
        elif level == "Normal":
            Domoticz.Log(message)

    def SensorTimedOut(self, idx, name, datestring):

        def LastUpdate(datestring):
            dateformat = "%Y-%m-%d %H:%M:%S"
            # the below try/except is meant to address an intermittent python bug in some embedded systems
            try:
                result = datetime.strptime(datestring, dateformat)
            except TypeError:
                result = datetime(*(time.strptime(datestring, dateformat)[0:6]))
            return result

        timedout = LastUpdate(datestring) + timedelta(minutes=int(Settings["SensorTimeout"])) < datetime.now()

        # handle logging of time outs... only log when status changes (less clutter in logs)
        if timedout:
            if self.ActiveSensors[idx]:
                Domoticz.Error("skipping timed out temperature sensor '{}'".format(name))
                self.ActiveSensors[idx] = False
        else:
            if not self.ActiveSensors[idx]:
                Domoticz.Status("previously timed out temperature sensor '{}' is back online".format(name))
                self.ActiveSensors[idx] = True

        return timedout


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

def WeatherMapAPI(APICall):

    jsonData = None
    url = "https://api.openweathermap.org/data/3.0/onecall?appid={}={}&lon={}&units=metric&lang=fr&exclude=minutely,hourly{}".format(Parameters["Password"], Parameters["Mode1"], Parameters["Mode2"], parse.quote(APICall, safe="&="))
    # ex : "https://api.openweathermap.org/data/3.0/onecall?appid=6b5f1c46010c3b99daba4f3ba529cfc4&lat=41.57387&lon=2.48982&units=metric&lang=fr&exclude=minutely,hourly"
    Domoticz.Debug("Calling OpenWeatherMap API: {}".format(url))
    try:
        req = request.Request(url)
        response = request.urlopen(req)
        if response.status == 200:
            jsonData = json.loads(response.read().decode('utf-8'))
            self.OutTemp = str(jsonData['current']['temp'])
            self.FeelTemp = str(jsonData['current']['feels_like'])
            self.TodayMinTemp = str(jsonData['daily']['temp']['min'])
            self.TodayMaxTemp = str(jsonData['current']['temp']['max'])

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

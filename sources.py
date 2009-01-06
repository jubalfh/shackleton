# Copyright (C) 2008 Ross Burton <ross@burtonini.com>
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51 Franklin
# St, Fifth Floor, Boston, MA 02110-1301 USA


import datetime, dbus, gobject

class Source(gobject.GObject):
    # TODO: Marco Polo has the neat ability for sources to suggest values for
    # the properties

    __gsignals__ = {
        'changed': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ())
        }
    
    def __init__(self, args):
        gobject.GObject.__init__(self)
    
    @staticmethod
    def getProperties():
        """A list of (name, type) pairs."""
        return ()

    def getPollInterval(self):
        # Return the number of seconds between polls if this source should be
        # polled, or 0 if it will fire signals when its evaluation state has
        # changed.
        raise NotImplementedError

    def evaluate(self, args):
        raise NotImplementedError
gobject.type_register(Source)

class DayOfWeekSource(Source):
    __instance = None
    def __new__(cls, args):
        # Make this a singleton
        if not cls.__instance:
            cls.__instance = super(cls,DayOfWeekSource).__new__(cls)
            Source.__init__(cls.__instance, args)
        return cls.__instance
    
    @staticmethod
    def getProperties():
        return (("weekday", list),)

    def getPollInterval(self):
        # Poll every minute
        # TODO: don't be a singleton and instead schedule a queue of wakeups and
        # emit signals.
        return 60

    def evaluate(self, args):
        weekday = args["weekday"]
        now = datetime.datetime.now().strftime("%A").lower()
        return now == weekday
gobject.type_register(DayOfWeekSource)

class TimeSource(Source):

    __instance = None
    def __new__(cls, args):
        # Make this a singleton
        if not cls.__instance:
            cls.__instance = super(cls,TimeSource).__new__(cls)
            Source.__init__(cls.__instance, args)
        return cls.__instance
    
    @staticmethod
    def getProperties():
        return (
            ("hour_start", int), ("minute_start", int),
            ("hour_end", int), ("minute_end", int),
            )

    def getPollInterval(self):
        # Poll every minute
        # TODO: don't be a singleton and instead schedule a queue of wakeups and
        # emit signals.
        return 60

    def evaluate(self, args):
        start = datetime.time(args["hour_start"], args["minute_start"])
        end = datetime.time(args["hour_end"], args["minute_end"])
        now = datetime.datetime.now().time()
        # This may look strange, but lets us do start=18:00 end=09:00
        if start < end:
            # Normal inclusive time slices
            return start < now < end
        else:
            # Exclusive time slices
            return now < end or now > start
gobject.type_register(TimeSource)


class WifiNetworkSource(Source):
    NM_STATE_CONNECTED = 3
    NM_STATE_DISCONNECTED = 4
    NM_DEVICE_TYPE_802_11_WIRELESS = 2
    
    __instance = None
    def __new__(cls, args):
        # Make this a singleton
        if not cls.__instance:
            s = super(cls,WifiNetworkSource).__new__(cls)
            Source.__init__(s, args)
            s.bus = dbus.SystemBus()
            s.nm = s.bus.get_object('org.freedesktop.NetworkManager', '/org/freedesktop/NetworkManager')
            s.nm.connect_to_signal("StateChange", s.state_changed)
            cls.__instance = s
        return cls.__instance
    
    @staticmethod
    def getProperties():
        return (("ssid", list),)
    
    def getPollInterval(self):
        return 0

    def state_changed(self, state):
        self.emit("changed")
    
    def evaluate(self, args):
        state = self.nm.state()
        if state != self.NM_STATE_CONNECTED:
            return False
        
        devices = self.nm.getDevices(dbus_interface='org.freedesktop.NetworkManager')
        for path in devices:
            device = self.bus.get_object('org.freedesktop.NetworkManager', path)
            props = device.getProperties()
            
            if props[2] != self.NM_DEVICE_TYPE_802_11_WIRELESS:
                # Device type is not wireless
                continue
            
            if not props[5]:
                # This device isn't active yet
                continue
            
            network_path = props[19]
            if not network_path:
                # No active network
                continue
            
            network = self.bus.get_object('org.freedesktop.NetworkManager', network_path)
            ssid = network.getProperties()[1]
            if ssid in args["ssid"]:
                return True
        
        return False
gobject.type_register(WifiNetworkSource)

class WicdNetworkDaemonSource(Source):
    __instance = None
    def __new__(cls, args):
        # Make this a singleton
        if not cls.__instance:
            s = super(cls,WicdNetworkDaemonSource).__new__(cls)
            Source.__init__(s, args)
            s.bus = dbus.SystemBus()
            s.wicd = s.bus.get_object('org.wicd.daemon', '/org/wicd/daemon')
            s.wicd.connect_to_signal("StatusChanged", s.state_changed)
            cls.__instance = s
        return cls.__instance
    
    @staticmethod
    def getProperties():
        return (("ssid", list),)
    
    def getPollInterval(self):
        return 0

    def state_changed(self, state, info):
        self.emit("changed")
    
    def evaluate(self, args):
        # NOTE: /wicd/wicd-daemon.py
        state, info = self.wicd.GetConnectionStatus()
        try:
            ssid = info[1]
            if ssid in args["ssid"]:
                return True
            else:
                return False
        except IndexError:
            return False
gobject.type_register(WicdNetworkDaemonSource)


class GConfSource(Source):
    __instances = {}
    def __new__(cls, args):
        # Have an instance per GConf key
        key = args["key"]
        if key not in cls.__instances:
            import gconf, os
            s = super(cls, GConfSource).__new__(cls)

            Source.__init__(s, args)
            client = gconf.client_get_default()
            client.add_dir(os.path.dirname(args["key"]), gconf.CLIENT_PRELOAD_NONE)
            client.notify_add(args["key"], s.key_changed)

            cls.__instances[key] = s
        return cls.__instances[key]
    
    @staticmethod
    def getProperties():
        return (("key", basestring), ("value", object))
    
    def getPollInterval(self):
        return 0
    
    def key_changed(self, client, id, entry, data):
        self.emit("changed")

    def evaluate(self, args):
        import gconf
        client = gconf.client_get_default()
        try:
            return client.get_value(args["key"]) == args["value"]
        except:
            return False
gobject.type_register(GConfSource)


class BatterySource(Source):

    __instance = None
    def __new__(cls, args):
        # Make this a singleton
        if not cls.__instance:
            s = super(cls, BatterySource).__new__(cls)
            Source.__init__(s, args)
            bus = dbus.SessionBus()
            s.pm = bus.get_object('org.freedesktop.PowerManagement', '/org/freedesktop/PowerManagement')
            s.pm.connect_to_signal("OnBatteryChanged", s.changed)
            cls.__instance = s
        return cls.__instance

    @staticmethod
    def getProperties():
        return (("on_battery", bool),)
    
    def getPollInterval(self):
        return 0
    
    def changed(self, bool):
        # TODO: cache the value and use it when evaluating to avoid DBus calls
        self.emit("changed")
    
    def evaluate(self, args):
        on_battery = self.pm.GetOnBattery()
        return on_battery == args["on_battery"]
gobject.type_register(BatterySource)


class VolumeDeviceSource(Source):
    """Matches the 'info.product' HAL property for a volume device, if you are
       unsure of the correct value, check 
       System->Preferences->Hardware Information, select your device on the left
       and switch to the advanced tab on the right. Locate the info.product key,
       the use the corressponding value."""

    def __init__(self, args):
        Source.__init__(self, args)
        self.bus = dbus.SystemBus()
        hal_obj = self.bus.get_object("org.freedesktop.Hal", 
                                     "/org/freedesktop/Hal/Manager")
        self.hal = dbus.Interface(hal_obj,
                                       "org.freedesktop.Hal.Manager")
        self.hal.connect_to_signal("DeviceAdded", self.list_changed)
        self.hal.connect_to_signal("DeviceRemoved", self.list_changed)
        self.device_name = args["device_name"]
        self.connected = self.check_connected_devices(self.device_name)

    @staticmethod
    def getProperties():
        return (("device_name", basestring),)
    
    def getPollInterval(self):
        return 0

    def evaluate(self, args):
        return self.connected

    def check_connected_devices(self, device_name):
        device_list = self.hal.FindDeviceByCapability("volume")
        
        for udi in device_list:
            volume = self.bus.get_object("org.freedesktop.Hal", udi)
            try:
                name = volume.GetProperty("info.product", 
                                   dbus_interface="org.freedesktop.Hal.Device")
                if name == device_name:
                    return True 
            except:
                pass
        return False

    def list_changed(self, *args):
        # Will check the list & set self.connected, so we don't need to poll
        self.connected = self.check_connected_devices(self.device_name)
        self.emit("changed")
gobject.type_register(VolumeDeviceSource) 


class AvahiSource(Source):
    def __init__(self, args):
        import avahi
        Source.__init__(self, args)

        self.name = args["name"]
        self.present = False
        
        bus = dbus.SystemBus()
        
        server = dbus.Interface(bus.get_object(avahi.DBUS_NAME, avahi.DBUS_PATH_SERVER),
                                avahi.DBUS_INTERFACE_SERVER)

        browser = dbus.Interface(bus.get_object(avahi.DBUS_NAME,
                                                server.ServiceBrowserNew(avahi.IF_UNSPEC, avahi.PROTO_UNSPEC,
                                                                         args["service_type"], "local", dbus.UInt32(0))),
                                 avahi.DBUS_INTERFACE_SERVICE_BROWSER)

        browser.connect_to_signal('ItemNew', self.service_new)
        browser.connect_to_signal('ItemRemove', self.service_removed)
    
    @staticmethod
    def getProperties():
        return (("service_type", basestring),
                ("name", basestring))
    
    def getPollInterval(self):
        return 0

    def service_new(self, interface, protocol, name, stype, domain, flags):
        if name == self.name:
            self.present = True
            self.emit("changed")
    
    def service_removed(self, interface, protocol, name, stype, domain, flags):
        if name == self.name:
            self.present = False
            self.emit("changed")
    
    def evaluate(self, args):
        return self.present
gobject.type_register(AvahiSource)


class BluetoothDeviceSource(Source):
    def __init__(self, args):
        Source.__init__(self, args)
        bus = dbus.SystemBus()

        try:
            # Grab the main bluez.Manager to find the default adapter
            obj = bus.get_object("org.bluez", "/org/bluez")
            self.manager = dbus.Interface(obj, "org.bluez.Manager")
            # Get the default adapter
            obj = bus.get_object("org.bluez", self.manager.DefaultAdapter())
            self.adapter = dbus.Interface(obj, "org.bluez.Adapter")
            self.adapter.connect_to_signal("DiscoveryStarted", 
                                           self.searchStarted)
            self.adapter.connect_to_signal("DiscoveryCompleted", 
                                           self.searchFinished)
            self.adapter.connect_to_signal("RemoteDeviceFound", 
                                           self.deviceFound)
            #set up the basic properties
            self.device_address = args["address"]
            self.connected = False
            self.device_list = []
            self.dirty = False
            self.no_connection = False
        except:
            self.no_connection = True

    @staticmethod
    def getProperties():
        return (("address", basestring),)
    
    def getPollInterval(self):
        if self.no_connection:
          return 0
        return 900 # Every 15 mins for now

    def evaluate(self, args):
        if self.no_connection:
          return False
        elif (self.dirty):
            self.dirty = False
            return self.connected
        else:
          self.checkConnectedDevices()
          return self.connected

    def checkConnectedDevices(self):
        self.adapter.DiscoverDevices() 

    def searchStarted(self):
        self.device_list = []

    def searchFinished(self):
        connected = False
        for address in self.device_list:
            if address == self.device_address:
                connected = True
                break
        if not connected == self.connected:
            self.connected = connected
            self.dirty = True
            self.emit("changed")

    def deviceFound(self, address, device_class, rssi):
        self.device_list.append(address)
gobject.type_register(BluetoothDeviceSource) 


class DeviceSource(Source):
    """Matches the HAL UDI for a device"""

    def __init__(self, args):
        Source.__init__(self, args)
        self.udi = args["udi"]

        self.bus = dbus.SystemBus()
        hal_obj = self.bus.get_object("org.freedesktop.Hal", 
                                     "/org/freedesktop/Hal/Manager")
        self.hal = dbus.Interface(hal_obj,
                                       "org.freedesktop.Hal.Manager")
        self.hal.connect_to_signal("DeviceAdded", self.device_added, arg0=self.udi)
        self.hal.connect_to_signal("DeviceRemoved", self.device_removed, arg0=self.udi)
        
        try:
            self.present = self.hal.DeviceExists(self.udi)
        except Exception, e:
            # Stupid HAL, see https://bugs.freedesktop.org/17082
            print e
            self.present = False

    @staticmethod
    def getProperties():
        return (("udi", basestring),)
    
    def getPollInterval(self):
        return 0

    def evaluate(self, args):
        return self.present

    def check_present(self, device_name):
        device_list = self.hal.FindDeviceByCapability("volume")
        
        for udi in device_list:
            volume = self.bus.get_object("org.freedesktop.Hal", udi)
            try:
                name = volume.GetProperty("info.product", 
                                   dbus_interface="org.freedesktop.Hal.Device")
                if name == device_name:
                    return True 
            except:
                pass
        return False

    def device_added(self, udi):
        if udi == self.udi:
            self.present = True
            self.emit("changed")

    def device_removed(self, udi):
        if udi == self.udi:
            self.present = False
            self.emit("changed")
gobject.type_register(DeviceSource)

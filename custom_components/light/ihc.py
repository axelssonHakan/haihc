"""
IHC light platform.
"""
# pylint: disable=too-many-arguments, too-many-instance-attributes, bare-except, unused-argument
import logging
import xml.etree.ElementTree
import voluptuous as vol
from homeassistant.components.light import (
    ATTR_BRIGHTNESS, SUPPORT_BRIGHTNESS, PLATFORM_SCHEMA, Light)
import homeassistant.helpers.config_validation as cv
from homeassistant.const import STATE_UNKNOWN
from ..ihc import IHCDevice, get_ihc_instance

DEPENDENCIES = ['ihc']

CONF_AUTOSETUP = 'autosetup'
CONF_IDS = 'ids'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_AUTOSETUP, default='False'): cv.boolean,
    vol.Optional(CONF_IDS): vol.Schema(vol.Required({cv.string: cv.string}))
})

PRODUCTAUTOSETUP = [
    #Wireless Combi dimmer 4 buttons
    {'xpath': './/product_airlink[@product_identifier="_0x4406"]',
     'node': 'airlink_dimming'},
    #Wireless Lampeudtag dimmer
    {'xpath': './/product_airlink[@product_identifier="_0x4306"]',
     'node': 'airlink_dimming'},
    #Wireless Lampeudtag relay
    {'xpath': './/product_airlink[@product_identifier="_0x4202"]',
     'node': 'airlink_relay'},
    #Wireless Combi relay 4 buttons
    {'xpath': './/product_airlink[@product_identifier="_0x4404"]',
     'node': 'airlink_relay'},
    # dataline lampeudtag
    {'xpath': './/product_dataline[@product_identifier="_0x2202"]',
     'node': 'dataline_output'},
]


_LOGGER = logging.getLogger(__name__)

_IHCLIGHTS = {}

def setup_platform(hass, config, add_devices_callback, discovery_info=None):
    """Setup the ihc lights platform"""
    ihccontroller = get_ihc_instance(hass)
    devices = []
    if config.get(CONF_AUTOSETUP):
        auto_setup(ihccontroller, devices)

    ids = config.get(CONF_IDS)
    if ids != None:
        _LOGGER.info("Adding/Changing IHC light names")
        for ihcid in ids:
            name = ids[ihcid]
            add_light(devices, ihccontroller, int(ihcid), name, True)

    add_devices_callback(devices)
    # Start notification after device har been added
    for device in devices:
        device.ihc.add_notify_event(device.get_ihcid(), device.on_ihc_change)


def auto_setup(ihccontroller, devices):
    """Auto setup ihc light product from ihc project """
    _LOGGER.info("Auto setup for IHC light")
    project = ihccontroller.get_project()
    xdoc = xml.etree.ElementTree.fromstring(project)
    groups = xdoc.findall(r'.//group')
    for group in groups:
        groupname = group.attrib['name']
        for productcfg in PRODUCTAUTOSETUP:
            products = group.findall(productcfg['xpath'])
            for product in products:
                node = product.find(productcfg['node'])
                ihcid = int(node.attrib['id'].strip('_'), 0)
                name = groupname + "_" + str(ihcid)
                add_light_from_node(devices, ihccontroller, ihcid, name, product)

class IhcLight(IHCDevice, Light):
    """Representation of a IHC light."""

    def __init__(self, ihccontroller, name, ihcid, ihcname, ihcnote, ihcposition):
        """Initialize the light."""
        IHCDevice.__init__(self, ihccontroller, name, ihcid, ihcname, ihcnote, ihcposition)
        self._brightness = 0
        self._dimmable = True
        self._state = STATE_UNKNOWN

    @property
    def should_poll(self) -> bool:
        """No polling needed for a ihc light."""
        return False

    @property
    def available(self) -> bool:
        """Return availability."""
        return True

    @property
    def brightness(self) -> int:
        """Return the brightness of this light between 0..255."""
        return self._brightness

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self._state

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        if self._dimmable:
            return SUPPORT_BRIGHTNESS
        return 0

    def turn_on(self, **kwargs) -> None:
        """Turn the light on."""
        self._state = True
        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs[ATTR_BRIGHTNESS]

        if self._dimmable:
            if self._brightness == 0:
                self._brightness = 255
            self.ihc.set_runtime_value_int(self._ihcid, int(self._brightness * 100 / 255))
        else:
            self.ihc.set_runtime_value_bool(self._ihcid, True)
        # As we have disabled polling, we need to inform
        # Home Assistant about updates in our state ourselves.
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        self._state = False

        if self._dimmable:
            self.ihc.set_runtime_value_int(self._ihcid, 0)
        else:
            self.ihc.set_runtime_value_bool(self._ihcid, False)
        # As we have disabled polling, we need to inform
        # Home Assistant about updates in our state ourselves.
        self.schedule_update_ha_state()

    def on_ihc_change(self, ihcid, value):
        """Callback from Ihc notifications"""
        try:
            if type(value) is int:
                self._dimmable = True
                self._brightness = value * 255 / 100
                self._state = self._brightness > 0
            else:
                self._dimmable = False
                self._state = value
            self.schedule_update_ha_state()
        except:
            pass

def add_light_from_node(devices, ihccontroller, ihcid: int, name: str, product) -> IhcLight:
    """Add a ihc light from a product node."""
    ihcname = product.attrib['name']
    ihcnote = product.attrib['note']
    ihcposition = product.attrib['position']
    return add_light(devices, ihccontroller, ihcid, name, False, ihcname, ihcnote, ihcposition)

def add_light(devices, ihccontroller, ihcid: int, name: str, overwrite: bool = False,
              ihcname: str = "", ihcnote: str = "", ihcposition: str = "") -> IhcLight:
    """Add a new ihc light"""
    if ihcid in _IHCLIGHTS:
        light = _IHCLIGHTS[ihcid]
        if overwrite:
            light.set_name(name)
            _LOGGER.info("IHC light set name: " + name + " " + str(ihcid))
    else:
        light = IhcLight(ihccontroller, name, ihcid, ihcname, ihcnote, ihcposition)
        _IHCLIGHTS[ihcid] = light
        devices.append(light)
        _LOGGER.info("IHC light added: " + name + " " + str(ihcid))
    return light

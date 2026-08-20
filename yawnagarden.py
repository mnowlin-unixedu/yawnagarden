import time
import math
import board
import busio
import smbus2 as smbus
from adafruit_bme280 import basic as adafruit_bme280
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
from influxdb_client import InfluxDBClient, Point

url = "http://localhost:8086"
token = "yourDBkey"
org = "garden"
bucket = "sensors"

# How often to poll/write
SLEEP_SECONDS = 5

# I2C addresses
BME_SUN_ADDR = 0x76
BME_SHADE_ADDR = 0x77
ADS1115_ADDR = 0x48
BH1750_SUN_ADDR = 0x23
BH1750_SHADE_ADDR = 0x5C

# DS18B20 path
DS18B20_PATH = "/sys/bus/w1/devices/28-000000245f21/w1_slave"

client = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api()

# I2C setup
# If the bus itself is down, the script will still keep retrying instead of exiting.
i2c = None
bus = None
bme_sun = None
bme_shade = None
ads = None
soil_east = None
soil_west = None


def log(msg):
    print(msg, flush=True)


def safe_call(label, func):
    """Run one sensor read without letting it kill the whole loop."""
    try:
        return func()
    except Exception as e:
        log(f"{label}: ERROR - {e}")
        return None


def ensure_i2c():
    global i2c, bus
    if i2c is None:
        i2c = busio.I2C(board.SCL, board.SDA)
    if bus is None:
        bus = smbus.SMBus(1)


def init_bme(address, name):
    def _init():
        ensure_i2c()
        return adafruit_bme280.Adafruit_BME280_I2C(i2c, address=address)
    return safe_call(f"{name} init 0x{address:02x}", _init)


def init_ads():
    def _init():
        ensure_i2c()
        a = ADS.ADS1115(i2c, address=ADS1115_ADDR)
        return a, AnalogIn(a, 0), AnalogIn(a, 1)
    result = safe_call(f"ADS1115 init 0x{ADS1115_ADDR:02x}", _init)
    if result is None:
        return None, None, None
    return result


def reinit_missing_sensors():
    global bme_sun, bme_shade, ads, soil_east, soil_west

    if bme_sun is None:
        bme_sun = init_bme(BME_SUN_ADDR, "BME sun")

    if bme_shade is None:
        bme_shade = init_bme(BME_SHADE_ADDR, "BME shade")

    if ads is None or soil_east is None or soil_west is None:
        ads, soil_east, soil_west = init_ads()


def f_from_c(temp_c):
    return (temp_c * 9 / 5) + 32


def read_bme(sensor):
    if sensor is None:
        return None
    # Read each property separately so a later failure is caught by safe_call.
    return {
        "temp_f": f_from_c(sensor.temperature),
        "humidity": sensor.humidity,
        "pressure": sensor.pressure,
    }


def read_bh1750(addr):
    ensure_i2c()
    bus.write_byte(addr, 0x10)
    time.sleep(0.18)
    data = bus.read_i2c_block_data(addr, 0x00, 2)
    raw = (data[0] << 8) | data[1]
    return raw / 1.2


def read_ds18b20():
    with open(DS18B20_PATH, "r") as f:
        lines = f.readlines()

    if not lines or "YES" not in lines[0]:
        return None

    temp_str = lines[1].split("t=")[-1]
    temp_c = float(temp_str) / 1000.0
    return f_from_c(temp_c)


def add_field(point, name, value):
    """Only write good numeric values to Influx.

    Bad/missing sensors are omitted, so Grafana shows no new stat for that field
    instead of the whole script dying.
    """
    if value is None:
        return point
    if isinstance(value, float) and math.isnan(value):
        return point
    return point.field(name, float(value))


def fmt(value, digits=2, unit=""):
    if value is None:
        return "ERROR"
    return f"{value:.{digits}f}{unit}"


while True:
    values = {}

    try:
        reinit_missing_sensors()

        sun = safe_call("BME sun read", lambda: read_bme(bme_sun))
        shade = safe_call("BME shade read", lambda: read_bme(bme_shade))

        if sun is not None:
            values["temp_sun"] = sun["temp_f"]
            values["humidity_sun"] = sun["humidity"]
            values["pressure_sun"] = sun["pressure"]
        else:
            bme_sun = None  # try fresh init next loop

        if shade is not None:
            values["temp_shade"] = shade["temp_f"]
            values["humidity_shade"] = shade["humidity"]
            values["pressure_shade"] = shade["pressure"]
        else:
            bme_shade = None  # try fresh init next loop

        values["light_sun"] = safe_call("BH1750 sun read", lambda: read_bh1750(BH1750_SUN_ADDR))
        values["light_shade"] = safe_call("BH1750 shade read", lambda: read_bh1750(BH1750_SHADE_ADDR))

        east = safe_call("Soil east read", lambda: soil_east.voltage if soil_east is not None else None)
        west = safe_call("Soil west read", lambda: soil_west.voltage if soil_west is not None else None)
        values["soileast_v"] = east
        values["soilwest_v"] = west
        if east is None or west is None:
            ads = soil_east = soil_west = None  # try fresh init next loop

        values["soil_temp"] = safe_call("DS18B20 soil temp read", read_ds18b20)

        point = Point("environment")
        fields_written = 0
        for field_name, field_value in values.items():
            if field_value is not None:
                point = add_field(point, field_name, field_value)
                fields_written += 1

        if fields_written > 0:
            write_api.write(bucket=bucket, org=org, record=point)
        else:
            log("No sensor fields available; skipped Influx write.")

        print("===== SENSOR READ =====")
        print(f"Temp Sun:       {fmt(values.get('temp_sun'), 2, ' F')}")
        print(f"Temp Shade:     {fmt(values.get('temp_shade'), 2, ' F')}")
        print(f"Humidity Sun:   {fmt(values.get('humidity_sun'), 2, ' %')}")
        print(f"Humidity Shade: {fmt(values.get('humidity_shade'), 2, ' %')}")
        print(f"Pressure Sun:   {fmt(values.get('pressure_sun'), 2, ' hPa')}")
        print(f"Pressure Shade: {fmt(values.get('pressure_shade'), 2, ' hPa')}")
        print(f"Light Sun:      {fmt(values.get('light_sun'), 2, ' lux')}")
        print(f"Light Shade:    {fmt(values.get('light_shade'), 2, ' lux')}")
        print(f"Soil East:      {fmt(values.get('soileast_v'), 3, ' V')}")
        print(f"Soil West:      {fmt(values.get('soilwest_v'), 3, ' V')}")
        print(f"Soil Temp:      {fmt(values.get('soil_temp'), 2, ' F')}")
        print(f"Influx fields written: {fields_written}")
        print("------------------------\n")

    except Exception as e:
        # Last-resort protection. A bad sensor should normally be caught above.
        log(f"MAIN LOOP ERROR: {e}")

    time.sleep(SLEEP_SECONDS)

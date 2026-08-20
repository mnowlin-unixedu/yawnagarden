# YAWNA Garden

**YAWNA Garden** is a Raspberry Pi-based garden monitoring system that collects environmental and soil data and stores it in InfluxDB for monitoring and visualization.

The system monitors conditions in both **sun** and **shade** areas of the garden, along with soil moisture and soil temperature. Sensor failures are handled independently so that a failed or disconnected sensor does not stop the entire monitoring system.

## What It Monitors

YAWNA Garden currently monitors:

* Air temperature in the sun
* Air temperature in the shade
* Relative humidity in the sun
* Relative humidity in the shade
* Atmospheric pressure in the sun
* Atmospheric pressure in the shade
* Light intensity in the sun
* Light intensity in the shade
* Soil moisture on the east side of the garden
* Soil moisture on the west side of the garden
* Soil temperature

Sensor readings are collected every **5 seconds** and written to InfluxDB.

## Hardware

### Raspberry Pi

The Raspberry Pi runs the Python monitoring program and communicates with the garden sensors.

The Pi also connects to the local InfluxDB database used to store sensor measurements.

### BME280 Environmental Sensors — 2

Two **BME280** sensors monitor the above-ground environment.

One is located in the **sun** and the other in the **shade**.

Each BME280 measures:

* Temperature
* Relative humidity
* Atmospheric pressure

The sensors use I2C.

Configured addresses:

| Location | I2C Address |
| -------- | ----------- |
| Sun      | `0x76`      |
| Shade    | `0x77`      |

Temperature readings are converted from Celsius to Fahrenheit by the Python program.

### BH1750 Light Sensors — 2

Two **BH1750 digital light sensors** measure the amount of light reaching different parts of the garden.

One measures the **sun** location and the other measures the **shade** location.

Measurements are recorded in **lux**.

Configured addresses:

| Location | I2C Address |
| -------- | ----------- |
| Sun      | `0x23`      |
| Shade    | `0x5C`      |

Having separate sun and shade sensors makes it possible to compare actual light exposure instead of relying only on time of day or weather conditions.

### Soil Moisture Sensors — 2

Two analog soil moisture sensors monitor moisture levels in different areas of the garden:

* **East soil sensor**
* **West soil sensor**

The Raspberry Pi cannot directly measure analog voltages, so the moisture sensors connect through an **ADS1115 analog-to-digital converter**.

The software currently records the raw sensor voltage rather than converting the measurement to a percentage.

InfluxDB fields:

* `soileast_v`
* `soilwest_v`

These voltage readings can be calibrated later against known dry and wet soil conditions if a moisture percentage is desired.

### ADS1115 Analog-to-Digital Converter

The **ADS1115** provides analog inputs for the two soil moisture sensors.

Configured I2C address:

`0x48`

Current channels:

| ADS1115 Channel | Sensor             |
| --------------- | ------------------ |
| A0              | East soil moisture |
| A1              | West soil moisture |

### DS18B20 Soil Temperature Sensor

A waterproof **DS18B20 digital temperature sensor** measures the temperature of the garden soil.

Unlike the other sensors, the DS18B20 uses the Raspberry Pi's **1-Wire** interface rather than I2C.

The Linux 1-Wire device is read from:

`/sys/bus/w1/devices/28-000000245f21/w1_slave`

The sensor reports Celsius natively, and YAWNA Garden converts the reading to **degrees Fahrenheit**.

## Sensor Layout

The monitoring system is essentially divided into these measurement areas:

**Sun**

* BME280 temperature
* BME280 humidity
* BME280 pressure
* BH1750 light level

**Shade**

* BME280 temperature
* BME280 humidity
* BME280 pressure
* BH1750 light level

**Soil**

* East soil moisture
* West soil moisture
* Soil temperature

This allows YAWNA Garden to compare the actual growing environment in different parts of the garden.

## Data Collection

The main Python program is:

`yawnagarden.py`

By default, the program polls the sensors every:

`5 seconds`

Each cycle attempts to read every available sensor.

The measurements are stored as fields under the InfluxDB measurement:

`environment`

Fields currently written include:

| Field            | Measurement                       |
| ---------------- | --------------------------------- |
| `temp_sun`       | Sun air temperature (°F)          |
| `temp_shade`     | Shade air temperature (°F)        |
| `humidity_sun`   | Sun relative humidity (%)         |
| `humidity_shade` | Shade relative humidity (%)       |
| `pressure_sun`   | Sun atmospheric pressure (hPa)    |
| `pressure_shade` | Shade atmospheric pressure (hPa)  |
| `light_sun`      | Sun light level (lux)             |
| `light_shade`    | Shade light level (lux)           |
| `soileast_v`     | East soil moisture sensor voltage |
| `soilwest_v`     | West soil moisture sensor voltage |
| `soil_temp`      | Soil temperature (°F)             |

## InfluxDB

YAWNA Garden uses the Python `influxdb-client` library to send measurements to a local InfluxDB server.

The current configuration expects:

`http://localhost:8086`

Organization:

`garden`

Bucket:

`sensors`

The InfluxDB API token must be configured before running the program.

Do **not** commit a real InfluxDB token to a public GitHub repository.

## Fault Tolerance

The monitoring program is designed so that one failed sensor does not shut down the entire garden monitoring system.

Each sensor read is protected by error handling.

If a sensor fails:

* The error is logged.
* Other working sensors continue to be read.
* Valid readings continue to be written to InfluxDB.
* Missing readings are omitted rather than storing invalid data.
* BME280 and ADS1115 devices are automatically reinitialized on later polling cycles if communication is lost.

This is useful for an outdoor monitoring system where wiring, moisture, connectors, or individual sensors may occasionally cause communication failures.

## Software Requirements

The project requires Python 3 and the following Python modules:

```text
adafruit-blinka
adafruit-circuitpython-bme280
adafruit-circuitpython-ads1x15
smbus2
influxdb-client
```

The Raspberry Pi must also have:

* I2C enabled
* 1-Wire enabled
* Access to InfluxDB
* Python 3

## Basic Installation

Clone the repository:

```bash
git clone https://github.com/mnowlin-unixedu/yawnagarden.git
cd yawnagarden
```

Install the required Python packages:

```bash
pip3 install adafruit-blinka \
    adafruit-circuitpython-bme280 \
    adafruit-circuitpython-ads1x15 \
    smbus2 \
    influxdb-client
```

Configure the InfluxDB settings near the top of `yawnagarden.py`:

```python
url = "http://localhost:8086"
token = "YOUR_INFLUXDB_TOKEN"
org = "garden"
bucket = "sensors"
```

Then run:

```bash
python3 yawnagarden.py
```

## Example Console Output

While running, YAWNA Garden displays the latest readings in the terminal:

```text
===== SENSOR READ =====
Temp Sun:       91.25 F
Temp Shade:     87.63 F
Humidity Sun:   43.20 %
Humidity Shade: 48.71 %
Pressure Sun:   1009.42 hPa
Pressure Shade: 1009.51 hPa
Light Sun:      68542.00 lux
Light Shade:    8241.00 lux
Soil East:      1.842 V
Soil West:      2.031 V
Soil Temp:      79.14 F
Influx fields written: 11
------------------------
```

The numbers above are only an example. Actual output depends on current garden conditions.

## Visualization

The data stored in InfluxDB can be visualized with **Grafana**.

This makes it possible to build dashboards showing trends such as:

* Sun vs. shade temperature
* Sun vs. shade humidity
* Daily light exposure
* East vs. west soil moisture
* Soil temperature
* Environmental changes throughout the day
* Historical garden conditions

## Project Structure

```text
yawnagarden/
├── yawnagarden.py
└── README.md
```

## Future Expansion

The system is designed so additional garden monitoring and automation features can be added later, such as:

* Additional soil moisture sensors
* Rain detection
* Water flow monitoring
* Irrigation valve control
* Automated watering based on soil moisture
* Additional temperature probes
* Weather data integration
* Alerts for extreme temperature or dry soil conditions

## Purpose

YAWNA Garden provides a simple, locally controlled way to collect real-world garden data using inexpensive sensors and a Raspberry Pi.

Instead of relying solely on general weather data, the system measures the actual conditions experienced by the plants — including differences between sunny and shaded areas and moisture conditions in different sections of the garden.

# AircraftTracker
Aircraft Tracking with Pan and Tilt Camera

**WIP**

## Key Design Decisions/Features

* two-part system: PT Camera Turret unit and ADS-B Receiver unit
  - PT camera mounted on a turret that receives target locations and streams video of the given target
  - ADS-B receiver with on-board processing and display
* the units communicate with each other via WiFi

* Camera unit
  - listens for target positions and directs the camera to follow the given target
  - on-board processor does track prediction by estimating target movement to smooth out tracking
    * the target position can be given as a tuple: e.g., (<lat>, <lon>, <alt>)
      - the on-board processor will convert to an (Az, El, {Zoom}) tuple
    * targets are identified by unique ids (e.g., ICAO hex numbers)
    * the target information should also include speed and altitude delta indications so that better track predictions can be made
    * assume that target updates are given at a rate of 1Hz
  - periodically sends current camera location and orientation
    * unclear at this point what the format should be and if messages should include timestamps
    * gets location from on-board GPS receiver
      - send when it changes and less frequently while in the same location
    * gets camera orientation from IMU mounted near the center of the camera's focal plane
      - sent more frequently when it changes and less frequently when it is static
      - send in most useful format -- e.g., Euler, Quaternion, etc.
  - use GPS to discipline on-board processor's RTC to generate good timestamps
  - camera optical zoom with auto-focus would be nice to have, but unlikely to fit the size and cost constraints
    * assume a telephoto lens, and zoom can be digital
  - video streams are sent over WiFi and can be viewed on any browser, or on the Receiver unit's display
  - command set includes a "no track" or "home" command to stop the camera from tracking and return it to the home orientation
    * could provide a home orientation -- e.g., based on most likely location of next track
  - turret driven by two stepper motors (each with a ULN2003 driver)
    * would like to allow unrestricted Az rotation, and El 180 deg from vertical
      - limit sensing shouldn't be needed given the IMU is there

* Receiver unit
  - has fully-functional ADS-B receivers -- i.e., 1090MHz, 980MHz, UAT, etc.
    * e.g., USBee1090U
  - has antennae for all ADS-B bands and WiFi
    * need to decide between external or internal antennae
      - should run some tests and measure signal strength, directionality, SWR, etc.
  - consider using RPi0-2W as on-board processing
    * useful to have full Linux, particularly for GUI
    * power consumption might be an issue
  - it's possible to have multiple implementations of the Receiver device
    * including both ESP32 and RasPi on-board processors, and a SW-only version running on a desktop machine
  - the Camera unit's GPS position and IMU orientation information is used to position icons on display relative to the Camera
    * consider adding an IMU to the Receiver unit to orient the display properly with respect to its physical orientation
  - has a touch-screen display to provide the desired display modes
    * radar mode
      - Camera unit in the center
      - 

  - can select a given aircraft to track from the list of current detected aircraft, or choose the Nth closest one to track

## Hardware

* 4" HDMI IPS LCD with Resistive Touch Screen
  - variation of: https://www.waveshare.com/wiki/4inch_HDMI_LCD
  - 

## Software

### Raspberry Pi Zero 2W

* LCD display



## Notes

--------------------------------------------------------------------------

## Key Features
* Range
  - Automatic: automatically select smallest (power of two Km) range that includes all current tracks
  - Manual: increase/decrease range in powers of two Km distances
* Trails (i.e., position points)
  - show position point history
  - can select no points, all points, or just the last 'N' points
* Aging of Tracks
  - enable/disable fade-out with time since last seen
* Summary
  - list of current tracks, sorted by distance from receiver
  - includes: flight number, altitude, speed, direction, distance, azimuth, and category
* Details
  - popup with detailed information on selected track
  - all current information about the track
* Filters
  - inside/outside altitude/speed range
  - categories
  - flight number (prefix)
  - uniqueIds
  - greater-/less-than distance
  - heading

## Interacting with the Application
* Command-line Arguments
  - *TBD*
* Touch Panel Inputs
  - *TBD*
* Keyboard Inputs
  - Left Arrow: reduce maximum number of trail points displayed
  - Right Arrow: increase maximum number of trail points displayed
  - Home: display no trail points
  - End: display all trail points
  - Up Arrow: increase the max distance to the next power of two Km
  - Down Arrow: decrease the max distance to the next power of two Km
  - 'a': auto-range -- enable auto-range mode
  - 'm': manual range -- disable auto-range mode
  - 'd': detail mode
  - 'i': info mode
  - 's': summary mode
  - 'p': print info
  - 'r': reset info
  - 'q': quit -- exit the application
  - 'h': print the keyboard inputs

## SW

### Raspberry Pi Zero 2W
* Set up for LCD Panel
  - install raspi os with 'rpi-imager'
* Update OS: 'apt update; apt upgrade'
* Update firmware with 'sudo rpi-update'
  - to fix HDMI issue with 5.15.56+
  - should be fixed in future releases
* disable audio
  - edit /boot/config.txt
    * add ",noaudio" to the end of "dtoverlay=vc4-kms-v3d"
    * comment out "dtparam=audio=on"
  - apt-get purge pulseaudio
* run 'raspi-config'
  - enable SPI, I2C, and UART (no console)

### 4" HDMI IPS LCD with Resistive Touch Screen
* Display works out of the box after standard SW setup
* Enable the touchpanel:
  - raspi-config puts this into /boot/config.txt:
    * dtparam=i2c_arm=on
    * dtparam=spi=on
    * dtoverlay=vc4-kms-v3d # I think this is there by default
  - add this:
    * dtoverlay=ads7846,cs=1,penirq=25,penirq_pull=2,speed=50000,keep_vref_on=0,swapxy=0,pmax=255,xohms=150,xmin=200,xmax=3900,ymin=200,ymax=3900
* Calibrate the touchpanel:
  - 'sudo apt-get install xserver-xorg-input-evdev xinput-calibrator'
  - 'sudo cp -rf /usr/share/X11/xorg.conf.d/10-evdev.conf /usr/share/X11/xorg.conf.d/45-evdev.conf'
  - 'sudo ex /usr/share/X11/xorg.conf.d/99-calibration.conf'
Section "InputClass"
        Identifier      "calibration"
        MatchProduct    "ADS7846 Touchscreen"
        Option  "Calibration"   "208 3905 288 3910"
        Option  "SwapAxes"      "0"
        Option "EmulateThirdButton" "1"
        Option "EmulateThirdButtonTimeout" "1000"
        Option "EmulateThirdButtonMoveThreshold" "300"
EndSection
  - 'sudo reboot'
* variation of: https://www.waveshare.com/wiki/4inch_HDMI_LCD

### RTL_SDR Receiver
* set permissions
  - 'lsusb' to get vendor Id and product Id
    * e.g., Bus 001 Device 005: ID 0bda:2832 Realtek Semiconductor Corp. RTL2832U DVB-T
  - create file '/etc/udev/rules.d/20.rtlsdr.rules'
    * add this content:
      - 'SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2832", GROUP="adm", MODE="0666", SYMLINK+="rtl_sdr"'

### GPS Receiver
* Enable serial port without console
  - using 'sudo raspi-config'
* Configure and test serial port
  - 'stty -F /dev/serial0 raw 9600 cs8 clocal -cstopb'
  - 'cat /dev/serial0'
    * should get NMEA strings from GPS unit
* N.B.
  - Using $GPGGA NMEA messages to get orientation information
  - Doing simple filtering of lat/lon
    * Assuming device not near poles/equator (where discontinuities occur)
  - Not using gpsd to reduce background load on the CPU

### 9DoF IMU
* RasPi didn't handle I2C clock-stretching properly
  - seems to work fine with PiZero V2
* install Adafruit BNO055 library from PyPi
  - 'sudo pip3 install adafruit-bno055'

### dump1090-fa
* set up environment
  - 'sudo apt-get install build-essential fakeroot debhelper librtlsdr-dev pkg-config libncurses5-dev libbladerf-dev libhackrf-dev liblimesuite-dev'
* clone dump1090-fa into ~/Code2/
  - 'git clone git@github.com:flightaware/dump1090.git'
* patch dump1090-fa to not write history files
  - e.g., as defined in dump1090.patch
* build modified dump1090-fa
  - './prepare-build.sh bullseye'
  - 'cd package-bullseye'
  - 'dpkg-buildpackage -b --no-sign'
* run dump1090 from pocket1090.sh
  - manual execution:
    * desktop:
      - '/home/jdn/Code2/dump1090/dump1090 --quiet --metric --json-stats-every 0 --write-json /tmp/
    * raspbian bullseye:
      - '/opt/pocket1090/dump1090 --quiet --metric --json-stats-every 0 --write-json /run/user/1000/

### pocket1090
* clone pocket1090 into ~/Code
  - 'git clone https://github.com/jduanen/pocket1090.git'
* Prepare SW Environment for the application
  - install 2.x pygame
    * 'pip3 install pygame==2.1'
      - Ubuntu: pygame 2.1.2 (SDL 2.0.16, Python 3.8.10)
      - RasPi: pygame 2.1.0 (SDL 2.0.14, python 3.9.2)
  - also install missing package:
    * 'sudo apt-get install libsdl2-image-2.0-0'
    * 'sudo apt install libsdl-gfx1.2-5 libsdl-image1.2 libsdl-kitchensink1 libsdl-mixer1.2 libsdl-sound1.2 libsdl-ttf2.0-0 libsdl1.2debian libsdl2-2.0-0 libsdl2-gfx-1.0-0 libsdl2-image-2.0-0 libsdl2-mixer-2.0-0 libsdl2-ttf-2.0-0'
  - 'pip3 install -r requirements.txt'
* install the pocket1090 application and supporting files (in /opt/pocket1090)
  - './pocket1090.sh install'
* run pocket1090 application
  - './pocket1090.sh start'
  - manual operation:
    * '/opt/pocket1090/pocket1090.py -v /run/user/1000 -L INFO -f'
      - run in full-screen mode
* pocket1090.sh
  - script to install, run, stop, get the status, and remove installation of pocket1090 application

### systemd
* install 'dump1090.service' and 'pocket1090.service' in '/lib/systemd/system'
  - change permissions: 'sudo chmod 644 /lib/systemd/system/{dump,pocket}1090.service'
* configure systemd
  - sudo systemctl daemon-reload
  - sudo systemctl start dump1090.service
  - sudo systemctl enable dump1090.service
  - sudo systemctl start pocket1090.service
  - sudo systemctl enable pocket1090.service
  - sudo reboot

## HW

### Enclosure

*WIP*

### Raspberry Pi Zero 2W
* https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/

### LCD Display
* https://www.waveshare.com/product/raspberry-pi/displays/4inch-hdmi-lcd.htm
* https://www.waveshare.com/wiki/4inch_HDMI_LCD
  - 4" 480x800 IPS LCD display
  - portrait-mode
  - 170 degree viewing angle
  - separate (micro-USB) power input for backlight
  - HDMI video input interface
  - resistive touch panel, XPT2046 controller
  - 3-/4-wire SPI interface to touch panel
  - 26pin dual-row connector
    * 1: 3.3V                   2: 5V
    * 3: SDA                    4: 5V
    * 5: SCL                    6: GND
    * 7: P7                     8: TX
    * 9: GND                   10: RX
    * 11: P0                   12: P1
    * 13: P2                   14: GND
    * 15: P3                   16: P4
    * 17: 3V3                  18: P5
    * 19: MOSI (TP SPI in)     20: GND
    * 21: MISO (TP SPI out)    22: P6 (TP IRQ)
    * 23: SCLK (TP SCLK)       24: CE0 (TP CS)
    * 25: GND                  26: CE1

### USBee1090U

* ?

### GPS Receiver
* https://www.adafruit.com/product/746
* GPS Receiver
  - 66 channel, 22 tracking
  - 10Hz updates, 34 secs warm/cold start
  - NMEA 0183, 9600 baud, 3V levels (5V tolerant)
  - PA1616S module, MTK3339
  - -165dBm sensitivity
  - 20mA
  - 3.3-5V input
  - battery-backed RTC, CR1220
  - Red Fix LED
    * blinks at ~1Hz while searching for satelites
    * blinks once every ~15 seconds when a fix is acheieved
  - PPS output
  - on-board patch antenna, u.FL connector
* pins
  - 3.3V (out)
  - ENB (in)
  - VBAT (in)
  - FIX (out)
  - TX (out)
  - RX (in)
  - GND
  - VIN (in)
  - PPS (out)
* RasPi Connection
  - GPIO 4:  ENB
  - GPIO 14: RX
  - GPIO 15: TX
  - 5V:      VIN
  - GND:     GND
  - GPIO 27: PPS

### 9DoF IMU
* https://www.adafruit.com/product/2472
* IMU
  - I2C interface, Address: 0x28, 10K pullups
    * might need 3.3K SCL and 2.2K SDA for 3.3V operation
  - auto-calibration
  - (black-box) sensor fusion
  - emits:
    * Euler Vector @ 100Hz
      - only use Euler Angles for pitch/roll < 45 degrees
    * Four Point Quaternion @ 100Hz
    * Angular Velocity Vector @ 100Hz
    * Accleration Vector @ 100Hz
    * Magnetic Field Strength Vector @ 20Hz
    * Linear Accleration Vector @ 100Hz
    * Gravity Vector @ 100Hz
    * Temperature @ 1Hz
  - N.B. highly sensitive to RF -- need to worry about placement/sheilding
* pins
  - VIN (in): 3-5V
  - 3VO (out): 3.3V output from regulator, < 50mA
  - GND
  - SCL (in): 3-5V, 10K pullup
  - SDA (bidir): 3-5V, 10K pullup
  - RST (in): reset on rising edge
  - P0: n/c
  - P1: n/c
  - INT (out): interrupt on motion, 3V
  - ADR (in): I2C address selection, 1=0x29, 0=0x28, 3V
* RasPi Connection
  - 3.3V:   VIN
  - GND:    GND
  - GPIO 2: SDA
  - GPIO 3: SCL
  - GPIO 5: DC

### Battery and Charger

*TBD*

### Antennae

*TBD*

------------------------------------------------------------------------------

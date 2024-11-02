#!/usr/bin/python3
import serial
import time
import threading
import sys
import re
import picamera2

plate_enable_re = re.compile('plt([0-9]+)_status')
plate_name_re = re.compile('plt([0-9]+)_name')

class MotorCtrl:
    def __init__(self):
        self.comm = serial.Serial(port='/tmp/printer')

    def flush(self):
        while ser.inWaiting() > 0:
            ser.read(ser.inWaiting())

    def send_gcode(self, gcode):
        self.comm.write(gcode)
        line = self.comm.read_until()
        while line != "ok":
            if line[:2] == "!!":
                continue
            else:
                print("Error: %s"%line)
                sys.exit(0)

class Magnet:
    def __init__(self, ctrl):
        self.ctrl = ctrl
        self.lock = threading.Lock()
        self.off_since = time.time()
        self.watchdog_thread = None

    def watchdog(self, shutdown_time):
        while shutdown_time > time.time() and self.lock.locked():
            time.sleep(1)
        if self.lock.locked():
            print("ERROR: magnet left on for too long")
            self.off()
            sys.exit(0)

    def on(self):
        time_off = time.time() - self.off_since
        max_time_on = min(time_off, 30)
        shutdown_time = time.time() + max_time_on
        self.lock.acquire()
        self.ctrl.send_gcode("SET_PIN PIN=magnet VALUE=1")
        self.watchdog_thread = threading.Thread(target=self.watchdog_thread, args=(shutdown_time))

    def off(self):
        self.lock.release()
        self.ctrl.send_gcode("SET_PIN PIN=magnet VALUE=0")

class Backend:
    plate_location = list(range(15, 21, 15+21*5)) + list(range(150, 21, 150+21*5))

    def __init__(self):
        self.comm = MotorCtrl()
        self.magnet = Magnet(self.comm)
        self.stop_thread = threading.Lock()
        self.plate_names = [""]*10
        self.plate_enabled = [False]*10
        self.freq = 6
        self.control_thread = None

    def home(self):
        self.comm.send_gcode("G28 X Z")

    def go_to(self, plate):
        self.comm.send_gcode("G0 Z"+self.plate_location[plate])

    def pull(self):
        self.comm.send_gcode("G0 X173")
        self.magnet.on()
        self.comm.send_gcode("G0 X0")
        self.magnet.off()

    def push(self):
        self.comm.send_gcode("G0 X170")
        self.comm.send_gcode("G0 X155")

    def disable_motors(self):
        self.comm.send_gcode("M18")

    def flash(self, on):
        self.comm.send_gcode("SET_PIN PIN=flash VALUE=%d"%(1 if on else 0))

    def take_pic(self):
        self.comm.send_gcode("G91")
        self.comm.send_gcode("G0 Z-5")
        self.flash(True)
        time.sleep(0.5) # TODO: take pic
        self.flash(False)
        self.comm.send_gcode("G0 Z5")
        self.comm.send_gcode("G90")

    def control_loop(self):
        while self.stop_thread.acquire(False) == False:
            self.home()

            for i in range(10):
                if self.stop_thread.acquire(False):
                    self.disable_motors()
                    return
                if self.plate_enabled[i]:
                    self.go_to(i)
                    self.pull()
                    self.take_pic()
                    self.push()

            self.disable_motors()
            if self.stop_thread.acquire(False):
                return
            time.sleep(self.freq * 60 * 60)

    def start(self):
        if self.control_thread == None or not self.control_thread.is_alive():
            self.stop_thread.acquire()
            self.control_thread = threading.Thread(target=self.control_loop)
            self.control_thread.start()
        else:
            print("already running!")

    def stop(self):
        try:
            self.stop_thread.release()
        except:
            print("already stopped!")

    def save(self, form):
        enabled = [False]*10
        names = [""]*10
        for key in form:
            if key == "freq":
                self.freq = form[key]
            elif plate_enable_re.match(key):
                plate = int(plate_enable_re.match(key).group(1))
                enabled[plate-1] = True
            elif plate_name_re.match(key):
                plate = int(plate_name_re.match(key).group(1))
                names[plate-1] = form[key]
            elif key == "action":
                pass
            else:
                print("unknown key: "+key)

        self.plate_names = names
        self.plate_enabled = enabled

#!/usr/bin/python3

from serial import Serial
import time
import threading
import sys

class MotorCtrl:
    def __init__(self):
        self.comm = Serial(port='/tmp/printer')

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
                print("Error: ")
                print(line)
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
    plate_location = list(range(15, 21, 15+21*5))

    def __init__(self):
        self.comm = MotorCtrl()
        self.magnet = Magnet(self.comm)

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

    def take_pic(self):
        pass # TODO

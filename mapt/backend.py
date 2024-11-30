#!/usr/bin/python3
import time
import threading
import sys
import sqlite3
import picamera2
import libcamera
import os
import serial
from libcamera import controls

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

class MotorCtrl:
    def __init__(self):
        self.comm = serial.Serial(port='/tmp/printer')
        self.flush()

    def flush(self):
        while self.comm.inWaiting() > 0:
            self.comm.read(self.comm.inWaiting())

    def send_gcode(self, gcode):
        print(gcode)
        gcode += "\n"
        self.comm.write(gcode.encode("utf-8"))
        line = self.comm.read_until().decode("utf-8")
        while line != "ok\n":
            if line[:2] == "!!":
                print(line)
            elif line[:2] == "//":
                print(line)
            elif line == "\n":
                pass
            else:
                eprint("Error: '%s'"%line)
                sys.exit(0)
            line = self.comm.read_until("\n")

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
            eprint("ERROR: magnet left on for too long")
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
    plate_location = list(range(12, 12+21*5, 21)) + list(range(125, 125+21*5, 21))

    def __init__(self):
        self.comm = MotorCtrl()
        self.magnet = Magnet(self.comm)
        self.stop_thread = threading.Lock()
        self.control_thread = None
        self.set_led(False)

        # init camera:
        self.cam = picamera2.Picamera2()
        self.calibrate_cam()
        self.cam.start(show_preview=False)
        self.flash(True)
        time.sleep(2)
        self.cam.set_controls({
                "AeEnable": False,
                "AwbEnable": False,
                "AfMode": controls.AfModeEnum.Manual, 
                "LensPosition": 8
            })
        self.flash(False)
        self.frame = self.cam.capture_array("main").tobytes()

        # init db:
        connection = sqlite3.connect("mapt.db")
        cursor = connection.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS plates (plate_num INTEGER PRIMARY KEY, name TEXT, status BOOL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY UNIQUE, value BLOB)")
        connection.commit()

        # load settings:
        plates = cursor.execute("SELECT * FROM plates").fetchall()
        try:
            self.freq = self.get_setting("freq")
        except:
            self.freq = None
        if len(plates) == 10:
            self.plate_names = [p[1] for p in plates]
            self.plate_enabled = [p[2] for p in plates]
        else:
            self.plate_names = [""]*10
            self.plate_enabled = [False]*10

        if self.get_setting("running"):
            eprint("resuming...")
            self.resume()

    def set_led(self, on):
        with open("/sys/class/leds/ACT/brightness", "w") as f:
            f.write("1" if on else "0")

    def calibrate_cam(self):
        # find the highest-quality image mode
        modes = self.cam.sensor_modes
        depth = max([m["bit_depth"] for m in modes])
        size = max([m["size"] if m["bit_depth"] == depth else (0,0) for m in modes])

        self.capture_config = self.cam.create_still_configuration(sensor={'output_size': size, 'bit_depth': depth}, queue=False)
        self.cam.configure(self.capture_config)

        #print(self.cam.camera_controls)
        #for i in self.cam.camera_controls:
        #    print(i)

    def home(self):
        self.comm.send_gcode("G28 X Z")

    def go_to(self, plate):
        self.comm.send_gcode("G0 Z"+str(self.plate_location[plate]))
        self.comm.send_gcode("M400")

    def pull(self):
        self.comm.send_gcode("G0 X129")
        self.comm.send_gcode("M400")
        self.magnet.on()
        self.comm.send_gcode("G0 X131")
        self.comm.send_gcode("G0 X3")
        self.comm.send_gcode("M400")
        self.magnet.off()
        time.sleep(1)
        self.comm.send_gcode("G0 X0")
        self.comm.send_gcode("M400")

    def push(self):
        self.comm.send_gcode("G0 X127")
        self.comm.send_gcode("G0 X120")
        self.comm.send_gcode("M400")

    def disable_motors(self):
        self.comm.send_gcode("M18")

    def flash(self, on):
        self.comm.send_gcode("SET_PIN PIN=flash VALUE=%d"%(1 if on else 0))

    def take_pic(self, plate):
        path = os.path.dirname(os.path.realpath(__file__))
        file_name = path+"/static/plate_%d_%s.jpg"%(plate+1, time.strftime("%Y-%m-%d-%H:%M:%S"))

        self.comm.send_gcode("G0 Z"+str(self.plate_location[plate]-12))
        self.flash(True)
        self.comm.send_gcode("G4 P2000")
        self.cam.switch_mode_and_capture_file(self.capture_config, file_name)
        self.flash(False)
        self.comm.send_gcode("G0 Z"+str(self.plate_location[plate]))
        self.comm.send_gcode("M400")

    def control_loop(self, start_time=None):
        def cleanup():
            self.stop_thread.release()
            self.disable_motors()
            self.set_led(False)

        self.set_led(True)
        while self.stop_thread.acquire(False) == False:
            # sleep if neccessary
            if start_time == None:
                start_time = time.time()
                self.save_setting("start_time", start_time)
            else:
                interval = self.freq * 60 * 60
                time_to_sleep = interval - (time.time()-start_time)%interval
                if time_to_sleep > 1:
                    time.sleep(1)
                    continue

            # TODO: change 'running' setting to 'state', to track whether power was lost while a plate was pulled out

            # take pics
            self.home()
            for i in range(10):
                if self.stop_thread.acquire(False):
                    cleanup()
                    return
                if self.plate_enabled[i]:
                    self.go_to(i)
                    self.pull()
                    self.take_pic(i)
                    self.push()
            self.comm.send_gcode("G0 X0 Z0")
            self.disable_motors()

        cleanup()

    def start(self):
        # TODO: use RPi status LED to show state
        if self.control_thread == None or not self.control_thread.is_alive():
            self.stop_thread.acquire()
            self.control_thread = threading.Thread(target=self.control_loop)
            self.control_thread.start()
            self.save_setting("running", True)
        else:
            eprint("already running!")

    def kill(self):
            self.stop_thread.release()

    def stop(self):
        try:
            self.save_setting("running", False)
            self.kill()
        except:
            eprint("already stopped!")

    # resume the main loop if the system restarted
    def resume(self):
        if self.control_thread == None or not self.control_thread.is_alive():
            self.stop_thread.acquire()
            self.control_thread = threading.Thread(target=self.control_loop, args=(self.get_setting("start_time"),))
            self.control_thread.start()
        else:
            eprint("already running!")

    # TODO: refactor this, move logic to flask app and use backend.save_setting() and backend.save_plates()
    def get_setting(self, key):
        cursor = sqlite3.connect("mapt.db").cursor()
        try:
            value = cursor.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()[0]
            return value
        except:
            return None

    def save_setting(self, key, value):
        connection = sqlite3.connect("mapt.db")
        cursor = connection.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        connection.commit()

    def get_plates(self):
        cursor = sqlite3.connect("mapt.db").cursor()
        return cursor.execute("SELECT * FROM plates").fetchall()

    def save_plates(self, names, status):
        connection = sqlite3.connect("mapt.db")
        cursor = connection.cursor()
        for i in range(10):
            cursor.execute("INSERT OR REPLACE INTO plates VALUES (?, ?, ?)", (i, names[i], status[i]))
        connection.commit()

    def get_frame(self):
        return self.frame

if __name__ == "__main__":
    b = Backend()
    b.home()
    while True:
        for plate in range(10):
            b.go_to(plate)
            b.pull()
            #b.take_pic(plate)
            b.push()
    b.comm.send_gcode("G0 X0 Z0")

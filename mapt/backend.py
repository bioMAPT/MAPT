#!/usr/bin/python3
import time
import threading
import sys
import re
import sqlite3

try:
    import serial
except:
    pass


#cursor.execute("CREATE TABLE IF NOT EXISTS settings (plate_num INTEGER PRIMARY KEY, name TEXT, status BOOL)")

plate_enable_re = re.compile('plt([0-9]+)_status')
plate_name_re = re.compile('plt([0-9]+)_name')

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
                print("Error: '%s'"%line)
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
    plate_location = list(range(12, 12+21*5, 21)) + list(range(125, 125+21*5, 21))

    def __init__(self):
        #self.comm = MotorCtrl()
        #self.magnet = Magnet(self.comm)
        self.stop_thread = threading.Lock()
        self.plate_names = [""]*10
        self.plate_enabled = [False]*10
        self.freq = 6
        self.control_thread = None
        try:
            import picamera2
            self.cam = picamera2.Picamera2()
            self.cam.start(show_preview=False)
            self.capture_config = self.cam.create_still_configuration()
            #self.calibrate_cam()
        except:
            pass

    def calibrate_cam(self):
        self.flash(True)
        self.cam.iso = 100
        self.cam.start_preview()
        time.sleep(2)
        self.cam.shutter_speed = self.cam.exposure_speed
        self.cam.exposure_mode = 'off'
        g = self.cam.awb_gains
        self.cam.awb_mode = 'off'
        self.cam.awb_gains = g
        self.flash(False)

    def home(self):
        self.comm.send_gcode("G28 X Z")

    def go_to(self, plate):
        self.comm.send_gcode("G0 Z"+str(self.plate_location[plate]))

    def pull(self):
        self.comm.send_gcode("G0 X129")
        self.magnet.on()
        self.comm.send_gcode("G0 X131")
        self.comm.send_gcode("G0 X3")
        self.magnet.off()
        time.sleep(1)
        self.comm.send_gcode("G0 X0")

    def push(self):
        self.comm.send_gcode("G0 X127")
        self.comm.send_gcode("G0 X120")

    def disable_motors(self):
        self.comm.send_gcode("M18")

    def flash(self, on):
        self.comm.send_gcode("SET_PIN PIN=flash VALUE=%d"%(1 if on else 0))

    def take_pic(self, plate):
        file_name = "plate_%d_%s.jpg"%(plate, time.strftime("%Y-%m-%d-%H:%M:%S"))

        self.comm.send_gcode("G0 Z"+str(self.plate_location[plate]-12))
        self.flash(True)
        self.comm.send_gcode("G4 P2000")
        self.cam.switch_mode_and_capture_file(self.capture_config, file_name)
        self.flash(False)
        self.comm.send_gcode("G0 Z"+str(self.plate_location[plate]))

    def control_loop(self):
        while self.stop_thread.acquire(False) == False:
            start_time = time.time()
            self.home()

            for i in range(10):
                if self.stop_thread.acquire(False):
                    self.stop_thread.release()
                    self.disable_motors()
                    return
                if self.plate_enabled[i]:
                    self.go_to(i)
                    self.pull()
                    self.take_pic(i)
                    self.push()

            self.disable_motors()
            if self.stop_thread.acquire(False):
                self.stop_thread.release()
                return
            time.sleep((self.freq * 60 * 60) - (time.time()-start_time))
        self.stop_thread.release()

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
        connection = sqlite3.connect("mapt.db")
        cursor = connection.cursor()
        enabled = [False]*10
        names = [""]*10
        for key in form:
            if key == "freq":
                self.freq = form[key]

            elif plate_enable_re.match(key):
                plate = int(plate_enable_re.match(key).group(1))
                print("enable", plate)
                print(key)
                enabled[plate] = True

            elif plate_name_re.match(key):
                plate = int(plate_name_re.match(key).group(1))
                print("name:",plate)
                print(key)
                names[plate] = form[key]

            elif key == "action":
                pass
            else:
                print("unknown key: "+key)

        self.plate_names = names
        self.plate_enabled = enabled

        for i in range(10):
            cursor.execute(f"INSERT OR REPLACE INTO settings VALUES ({i}, '{self.plate_names[i]}', '{self.plate_enabled[i]}')")
            print(f"INSERT OR REPLACE INTO settings VALUES ({i}, '{self.plate_names[i]}', '{self.plate_enabled[i]}')")
        connection.commit()

    def get_settings(self):
        connection = sqlite3.connect("mapt.db")
        cursor = connection.cursor()
        print("TEST")
        cur = cursor.execute("SELECT * FROM settings").fetchall()
        print("SQL: ",cur)
        return cur



if __name__ == "__main__":
    b = Backend()
    b.home()
    while True:
        for plate in range(len(b.plate_location)):
            b.go_to(plate)
            b.pull()
            b.take_pic(plate)
            b.push()

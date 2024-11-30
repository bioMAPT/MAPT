from flask import Flask, render_template, request, Response
import re
import os
from waitress import serve
import time

from .backend import Backend

plate_enable_re = re.compile('plt([0-9]+)_status')
plate_name_re = re.compile('plt([0-9]+)_name')

backend = Backend()

app=Flask(__name__, template_folder='templates')

@app.route('/', methods=["POST", "GET"])
def index():
    if request.method == "POST":
        if request.form["action"] == "start":
            backend.start()
        elif request.form["action"] == "stop":
            backend.stop()
        elif request.form["action"] == "save":
            names = [""]*10
            status = [False]*10
            form = dict(request.form)
            for key in form:
                if key == "freq":
                    backend.save_setting("freq", int(form[key]))
                elif plate_enable_re.match(key):
                    plate = int(plate_enable_re.match(key).group(1))
                    status[plate] = True
                elif plate_name_re.match(key):
                    plate = int(plate_name_re.match(key).group(1))
                    name = key
                    names[plate] = form[key]
                elif key == "action":
                    pass
                else:
                    print("unknown key: "+key)

            backend.save_plates(names, status)

    freq = backend.get_setting("freq")
    running = backend.get_setting("running")

    plates = backend.get_plates()
    if len(plates) != 10:
        plates = [[None, "", False] for i in range(10)]

    return render_template("index.html", plates=plates, freq=freq, running=running)

@app.context_processor
def template_functions():
    def get_pictures():
        return os.listdir(os.path.dirname(os.path.realpath(__file__))+"/static")
    return dict(get_pictures=get_pictures)


@app.route("/pics", methods=["GET"])
def pics():
    return render_template("pics.html")

def stream():
    count = 0
    while True:
        frame = backend.get_frame()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(stream(), mimetype='multipart/x-mixed-replace; boundary=frame')


if __name__ == '__main__':
    serve(app, listen="*:80")
    print('app exited')
    backend.kill()

from flask import Flask, render_template, request
from waitress import serve

from .backend import Backend

backend = Backend()

app=Flask(__name__, template_folder='templates')

settings={"plt1_name":"",
          "plt2_name":"",
          "plt3_name":"",
          "plt4_name":"",
          "plt5_name":"",
          "plt6_name":"",
          "plt7_name":"",
          "plt8_name":"",
          "plt9_name":"",
          "plt10_name":""}

@app.route('/', methods=["POST", "GET"])
def index():
    if request.method == "POST":
        if request.form["action"] == "start":
            backend.start()
        elif request.form["action"] == "stop":
            backend.stop()
        elif request.form["action"] == "save":
            backend.save(request.form)
    return render_template("index.html")

if __name__ == '__main__':
    serve(app, listen="*:80")

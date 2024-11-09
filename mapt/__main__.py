from flask import Flask, render_template, request
from waitress import serve

from .backend import Backend

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
            backend.save(request.form)
    print(backend.get_settings())
    plt_name=[row[1] for row in backend.get_settings()]
    plt_status=[row[2] == "True" for row in backend.get_settings()]
    return render_template("index.html", plt_name=plt_name, plt_status=plt_status)


if __name__ == '__main__':
    serve(app, listen="*:80")

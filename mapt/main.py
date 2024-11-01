from flask import Flask, render_template, request

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

@app.route('/register_press', methods=["POST"])
def register_press():
        print("Start")
        return "Button press registered successfully!"

@app.route('/')
def index():
    return render_template("index.html")

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)



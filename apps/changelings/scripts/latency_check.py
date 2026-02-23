import modal

image = modal.Image.debian_slim().pip_install("flask")
app = modal.App(name="latency_check", image=image)


@app.function(image=image, scaledown_window=5, cloud="oci")
@modal.concurrent(max_inputs=100)
@modal.wsgi_app()
def flask_app():
    from flask import Flask
    from flask import request

    web_app = Flask(__name__)

    @web_app.post("/echo")
    def echo():
        return request.json

    return web_app


# app = modal.App(name="latency_check")
#
# @app.function(scaledown_window=5)
# @modal.concurrent(max_inputs=100)
# @modal.web_server(8000)
# def my_file_server():
#     import subprocess
#     subprocess.Popen("python -m http.server -d / 8000", shell=True)

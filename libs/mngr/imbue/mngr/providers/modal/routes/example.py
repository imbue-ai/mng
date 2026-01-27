import modal

image = modal.Image.debian_slim().uv_pip_install("fastapi[standard]")
app = modal.App(name="mngr-8caed3bc40df435fae5817ea0afdbf77-modal", image=image)


@app.function()
@modal.fastapi_endpoint(
    docs=True  # adds interactive documentation in the browser
)
def hello():
    return "Hello world!"

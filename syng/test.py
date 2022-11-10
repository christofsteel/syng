import socketio


def append_yt(url):
    sio = socketio.Client()
    sio.connect("http://localhost:8080")
    sio.emit("append", {"source": "youtube", "id": url, "performer": "test"})
    sio.disconnect()


def skip():
    sio = socketio.Client()
    sio.connect("http://localhost:8080")
    sio.emit("register-admin", {"secret": "admin"})
    sio.emit("skip")
    sio.disconnect()


def search(query):
    sio = socketio.Client()
    sio.on("search-result", print)
    sio.connect("http://localhost:8080")
    sio.emit("search", {"query": query})
    sio.disconnect()

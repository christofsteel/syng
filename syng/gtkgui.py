import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gdk


appname = "rocks.syng.Syng"
# appname = "org.inkscape.Inkscape"
# appname = "kdenlive"
#


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_icon_name(appname)


class MyApp(Adw.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        win = MainWindow(application=app)
        win.set_title("Syng")
        win.present()


def run_gui():
    GLib.set_prgname(appname)
    Gtk.Window.set_default_icon_name(appname)
    app = MyApp(application_id=appname)
    app.run()


if __name__ == "__main__":
    run_gui()

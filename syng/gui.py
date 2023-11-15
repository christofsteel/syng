import asyncio
from datetime import datetime, date, time
import os
import builtins
from functools import partial
import webbrowser
import PIL
from yaml import load, Loader
import multiprocessing
import customtkinter
import qrcode
import secrets
import string
from tkinter import PhotoImage, filedialog
from tkcalendar import Calendar
from tktimepicker import SpinTimePickerOld, AnalogPicker, AnalogThemes
from tktimepicker import constants

from .client import create_async_and_start_client, default_config, start_client

from .sources import available_sources
from .server import main as server_main


class DateAndTimePickerWindow(customtkinter.CTkToplevel):
    def __init__(self, parent, input_field):
        super().__init__(parent)

        try:
            iso_string = input_field.get("0.0", "end").strip()
            selected = datetime.fromisoformat(iso_string)
        except ValueError:
            selected = datetime.now()

        self.calendar = Calendar(self)
        self.calendar.pack(
            expand=True,
            fill="both",
        )
        self.timepicker = AnalogPicker(
            self,
            type=constants.HOURS12,
            period=constants.AM if selected.hour < 12 else constants.PM,
        )
        theme = AnalogThemes(self.timepicker)
        theme.setDracula()

        self.calendar.selection_set(selected)
        self.timepicker.setHours(selected.hour % 12)
        self.timepicker.setMinutes(selected.minute)

        self.timepicker.pack(expand=True, fill="both")

        button = customtkinter.CTkButton(
            self, text="Ok", command=partial(self.insert, input_field)
        )
        button.pack(expand=True, fill="x")

    def insert(self, input_field: customtkinter.CTkTextbox):
        input_field.delete("0.0", "end")
        selected_date = self.calendar.selection_get()
        if not isinstance(selected_date, date):
            return
        hours, minutes, ampm = self.timepicker.time()
        hours = hours % 12
        if ampm == "PM":
            hours = hours + 12

        selected_datetime = datetime.combine(selected_date, time(hours, minutes))
        input_field.insert("0.0", selected_datetime.isoformat())
        self.withdraw()
        self.destroy()


class OptionFrame(customtkinter.CTkScrollableFrame):
    def add_option_label(self, text):
        customtkinter.CTkLabel(self, text=text, justify="left").grid(
            column=0, row=self.number_of_options, padx=5, pady=5, sticky="ne"
        )

    def add_bool_option(self, name, description, value=False):
        self.add_option_label(description)
        self.bool_options[name] = customtkinter.CTkCheckBox(
            self,
            text="",
            onvalue=True,
            offvalue=False,
        )
        if value:
            self.bool_options[name].select()
        else:
            self.bool_options[name].deselect()
        self.bool_options[name].grid(column=1, row=self.number_of_options, sticky="EW")
        self.number_of_options += 1

    def add_string_option(self, name, description, value="", callback=None):
        self.add_option_label(description)
        if value is None:
            value = ""

        self.string_options[name] = customtkinter.CTkTextbox(
            self, wrap="none", height=1
        )
        self.string_options[name].grid(
            column=1, row=self.number_of_options, sticky="EW"
        )
        self.string_options[name].insert("0.0", value)
        if callback is not None:
            self.string_options[name].bind("<KeyRelease>", callback)
            self.string_options[name].bind("<ButtonRelease>", callback)
        self.number_of_options += 1

    def del_list_element(self, name, element, frame):
        self.list_options[name].remove(element)
        frame.destroy()

    def add_list_element(self, name, frame, init, callback):
        input_and_minus = customtkinter.CTkFrame(frame)
        input_and_minus.pack(side="top", fill="x", expand=True)
        input_field = customtkinter.CTkTextbox(input_and_minus, wrap="none", height=1)
        input_field.pack(side="left", fill="x", expand=True)
        input_field.insert("0.0", init)
        if callback is not None:
            input_field.bind("<KeyRelease>", callback)
            input_field.bind("<ButtonRelease>", callback)

        minus_button = customtkinter.CTkButton(
            input_and_minus,
            text="-",
            width=40,
            command=partial(self.del_list_element, name, input_field, input_and_minus),
        )
        minus_button.pack(side="right")
        self.list_options[name].append(input_field)

    def add_list_option(self, name, description, value=[], callback=None):
        self.add_option_label(description)

        frame = customtkinter.CTkFrame(self)
        frame.grid(column=1, row=self.number_of_options, sticky="EW")

        self.list_options[name] = []
        for v in value:
            self.add_list_element(name, frame, v, callback)
        plus_button = customtkinter.CTkButton(
            frame,
            text="+",
            command=partial(self.add_list_element, name, frame, "", callback),
        )
        plus_button.pack(side="bottom", fill="x", expand=True)

        self.number_of_options += 1

    def add_choose_option(self, name, description, values, value=""):
        self.add_option_label(description)
        self.choose_options[name] = customtkinter.CTkOptionMenu(self, values=values)
        self.choose_options[name].grid(
            column=1, row=self.number_of_options, sticky="EW"
        )
        self.choose_options[name].set(value)
        self.number_of_options += 1

    def open_date_and_time_picker(self, name, input_field):
        if (
            name not in self.date_and_time_pickers
            or not self.date_and_time_pickers[name].winfo_exists()
        ):
            self.date_and_time_pickers[name] = DateAndTimePickerWindow(
                self, input_field
            )
        else:
            self.date_and_time_pickers[name].focus()

    def add_date_time_option(self, name, description, value):
        self.add_option_label(description)
        self.date_time_options[name] = None
        input_and_button = customtkinter.CTkFrame(self)
        input_and_button.grid(column=1, row=self.number_of_options, sticky="EW")
        input_field = customtkinter.CTkTextbox(input_and_button, wrap="none", height=1)
        input_field.pack(side="left", fill="x", expand=True)
        try:
            datetime.fromisoformat(value)
        except TypeError:
            value = ""
        input_field.insert("0.0", value)

        button = customtkinter.CTkButton(
            input_and_button,
            text="...",
            width=40,
            command=partial(self.open_date_and_time_picker, name, input_field),
        )
        button.pack(side="right")
        self.number_of_options += 1

    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure((1,), weight=1)
        self.number_of_options = 0
        self.string_options = {}
        self.choose_options = {}
        self.bool_options = {}
        self.list_options = {}
        self.date_time_options = {}
        self.date_and_time_pickers = {}

    def get_config(self):
        config = {}
        for name, textbox in self.string_options.items():
            config[name] = textbox.get("0.0", "end").strip()

        for name, optionmenu in self.choose_options.items():
            config[name] = optionmenu.get().strip()

        for name, checkbox in self.bool_options.items():
            config[name] = checkbox.get() == 1

        for name, textboxes in self.list_options.items():
            config[name] = []
            for textbox in textboxes:
                config[name].append(textbox.get("0.0", "end").strip())

        return config


class SourceTab(OptionFrame):
    def updateStrVar(self, var: str, element: customtkinter.CTkTextbox, event):
        value = element.get("0.0", "end").strip()
        self.vars[var] = value

    def updateBoolVar(self, var: str, element: customtkinter.CTkCheckBox, event):
        value = True if element.get() == 1 else False
        self.vars[var] = value

    def updateListVar(self, var: str, element: customtkinter.CTkTextbox, event):
        value = [v.strip() for v in element.get("0.0", "end").strip().split(",")]
        self.vars[var] = value

    def __init__(self, parent, source_name, config):
        super().__init__(parent)
        source = available_sources[source_name]
        self.vars: dict[str, str | bool | list[str]] = {}
        for name, (typ, desc, default) in source.config_schema.items():
            value = config[name] if name in config else default
            match typ:
                case builtins.bool:
                    self.add_bool_option(name, desc, value=value)
                case builtins.list:
                    self.add_list_option(name, desc, value=value)
                case builtins.str:
                    self.add_string_option(name, desc, value=value)


class GeneralConfig(OptionFrame):
    def __init__(self, parent, config, callback):
        super().__init__(parent)

        self.add_string_option("server", "Server", config["server"], callback)
        self.add_string_option("room", "Room", config["room"], callback)
        self.add_string_option("secret", "Secret", config["secret"])
        self.add_choose_option(
            "waiting_room_policy",
            "Waiting room policy",
            ["forced", "optional", "none"],
            str(config["waiting_room_policy"]).lower(),
        )
        # self.add_string_option(
        #     "last_song", "Time of last song\nin ISO-8601", config["last_song"]
        # )
        self.add_date_time_option("last_song", "Time of last song", config["last_song"])
        self.add_string_option(
            "preview_duration", "Preview Duration", config["preview_duration"]
        )

    def get_config(self):
        config = super().get_config()
        try:
            config["preview_duration"] = int(config["preview_duration"])
        except ValueError:
            config["preview_duration"] = 0

        return config


class SyngGui(customtkinter.CTk):
    def loadConfig(self):
        filedialog.askopenfilename()

    def on_close(self):
        if self.server is not None:
            self.server.kill()

        if self.client is not None:
            self.client.kill()

        self.withdraw()
        self.destroy()

    def __init__(self):
        super().__init__(className="Syng")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        rel_path = os.path.dirname(__file__)
        img = PIL.ImageTk.PhotoImage(file=os.path.join(rel_path, "static/syng.png"))
        self.wm_iconbitmap()
        self.iconphoto(False, img)

        self.server = None
        self.client = None

        try:
            with open("syng-client.yaml") as cfile:
                loaded_config = load(cfile, Loader=Loader)
        except FileNotFoundError:
            loaded_config = {}
        config = {"sources": {}, "config": default_config()}
        if "config" in loaded_config:
            config["config"] |= loaded_config["config"]

        if not config["config"]["secret"]:
            config["config"]["secret"] = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(8)
            )

        self.wm_title("Syng")

        # Buttons
        fileframe = customtkinter.CTkFrame(self)
        fileframe.pack(side="bottom")

        loadbutton = customtkinter.CTkButton(
            fileframe,
            text="load",
            command=self.loadConfig,
        )
        loadbutton.pack(side="left")

        self.startbutton = customtkinter.CTkButton(
            fileframe, text="Start", command=self.start_client
        )
        self.startbutton.pack(side="right")

        # startserverbutton = customtkinter.CTkButton(
        #     fileframe, text="Start Server", command=self.start_server
        # )
        # startserverbutton.pack(side="right")

        open_web_button = customtkinter.CTkButton(
            fileframe, text="Open Web", command=self.open_web
        )
        open_web_button.pack(side="left")

        # Tabs and QR Code
        frm = customtkinter.CTkFrame(self)
        frm.pack(ipadx=10, padx=10, fill="both", expand=True)

        tabview = customtkinter.CTkTabview(frm, width=600, height=500)
        tabview.pack(side="right", padx=10, pady=10, fill="both", expand=True)

        tabview.add("General")
        for source in available_sources:
            tabview.add(source)
        tabview.set("General")

        self.qrlabel = customtkinter.CTkLabel(frm, text="")
        self.qrlabel.pack(side="left", anchor="n", padx=10, pady=10)

        self.general_config = GeneralConfig(
            tabview.tab("General"), config["config"], self.updateQr
        )
        self.general_config.pack(ipadx=10, fill="both", expand=True)

        self.tabs = {}

        for source_name in available_sources:
            try:
                source_config = loaded_config["sources"][source_name]
            except KeyError:
                source_config = {}

            self.tabs[source_name] = SourceTab(
                tabview.tab(source_name), source_name, source_config
            )
            self.tabs[source_name].pack(ipadx=10, expand=True, fill="both")

        self.updateQr()

    def start_client(self):
        if self.client is None:
            sources = {}
            for source, tab in self.tabs.items():
                sources[source] = tab.get_config()

            general_config = self.general_config.get_config()

            config = {"sources": sources, "config": general_config}
            self.client = multiprocessing.Process(
                target=create_async_and_start_client, args=(config,)
            )
            self.client.start()
            self.startbutton.configure(text="Stop")
        else:
            self.client.terminate()
            self.client = None
            self.startbutton.configure(text="Start")

    def start_server(self):
        self.server = multiprocessing.Process(target=server_main)
        self.server.start()

    def open_web(self):
        config = self.general_config.get_config()
        server = config["server"]
        server += "" if server.endswith("/") else "/"
        room = config["room"]
        webbrowser.open(server + room)

    def changeQr(self, data: str):
        qr = qrcode.QRCode(box_size=20, border=2)
        qr.add_data(data)
        qr.make()
        qr.print_ascii()
        image = qr.make_image().convert("RGB")
        tkQrcode = customtkinter.CTkImage(light_image=image, size=(280, 280))
        self.qrlabel.configure(image=tkQrcode)

    def updateQr(self, _evt=None):
        config = self.general_config.get_config()
        server = config["server"]
        server += "" if server.endswith("/") else "/"
        room = config["room"]
        print(server + room)
        self.changeQr(server + room)


def main():
    SyngGui().mainloop()


if __name__ == "__main__":
    main()

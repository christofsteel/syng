from multiprocessing import Process
from collections.abc import Callable
from datetime import datetime, date, time
import os
import builtins
from functools import partial
from typing import Any, Optional
import webbrowser
import multiprocessing
import secrets
import string

from PIL import ImageTk
from yaml import dump, load, Loader, Dumper
import customtkinter
from qrcode import QRCode
from tkcalendar import Calendar
from tktimepicker import AnalogPicker, AnalogThemes, constants
import platformdirs

from .client import create_async_and_start_client, default_config

from .sources import available_sources

try:
    from .server import main as server_main

    SERVER_AVAILABLE = True
except ImportError:
    SERVER_AVAILABLE = False


class DateAndTimePickerWindow(customtkinter.CTkToplevel):  # type: ignore
    def __init__(
        self,
        parent: customtkinter.CTkFrame | customtkinter.CTkScrollableFrame,
        input_field: customtkinter.CTkTextbox,
    ) -> None:
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

        button = customtkinter.CTkButton(self, text="Ok", command=partial(self.insert, input_field))
        button.pack(expand=True, fill="x")

    def insert(self, input_field: customtkinter.CTkTextbox) -> None:
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


class OptionFrame(customtkinter.CTkScrollableFrame):  # type:ignore
    def add_option_label(self, text: str) -> None:
        customtkinter.CTkLabel(self, text=text, justify="left").grid(
            column=0, row=self.number_of_options, padx=5, pady=5, sticky="ne"
        )

    def add_bool_option(self, name: str, description: str, value: bool = False) -> None:
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

    def add_string_option(
        self,
        name: str,
        description: str,
        value: str = "",
        callback: Optional[Callable[..., None]] = None,
    ) -> None:
        self.add_option_label(description)
        if value is None:
            value = ""

        self.string_options[name] = customtkinter.CTkTextbox(self, wrap="none", height=1)
        self.string_options[name].grid(column=1, row=self.number_of_options, sticky="EW")
        self.string_options[name].insert("0.0", value)
        if callback is not None:
            self.string_options[name].bind("<KeyRelease>", callback)
            self.string_options[name].bind("<ButtonRelease>", callback)
        self.number_of_options += 1

    def del_list_element(
        self,
        name: str,
        element: customtkinter.CTkTextbox,
        frame: customtkinter.CTkFrame,
    ) -> None:
        self.list_options[name].remove(element)
        frame.destroy()

    def add_list_element(
        self,
        name: str,
        frame: customtkinter.CTkFrame,
        init: str,
        callback: Optional[Callable[..., None]],
    ) -> None:
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

    def add_list_option(
        self,
        name: str,
        description: str,
        value: list[str],
        callback: Optional[Callable[..., None]] = None,
    ) -> None:
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

    def add_choose_option(
        self, name: str, description: str, values: list[str], value: str = ""
    ) -> None:
        self.add_option_label(description)
        self.choose_options[name] = customtkinter.CTkOptionMenu(self, values=values)
        self.choose_options[name].grid(column=1, row=self.number_of_options, sticky="EW")
        self.choose_options[name].set(value)
        self.number_of_options += 1

    def open_date_and_time_picker(self, name: str, input_field: customtkinter.CTkTextbox) -> None:
        if (
            name not in self.date_and_time_pickers
            or not self.date_and_time_pickers[name].winfo_exists()
        ):
            self.date_and_time_pickers[name] = DateAndTimePickerWindow(self, input_field)
        else:
            self.date_and_time_pickers[name].focus()

    def add_date_time_option(self, name: str, description: str, value: str) -> None:
        self.add_option_label(description)
        input_and_button = customtkinter.CTkFrame(self)
        input_and_button.grid(column=1, row=self.number_of_options, sticky="EW")
        input_field = customtkinter.CTkTextbox(input_and_button, wrap="none", height=1)
        input_field.pack(side="left", fill="x", expand=True)
        self.date_time_options[name] = input_field
        try:
            datetime.fromisoformat(value)
        except (TypeError, ValueError):
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

    def __init__(self, parent: customtkinter.CTkFrame) -> None:
        super().__init__(parent)
        self.columnconfigure((1,), weight=1)
        self.number_of_options: int = 0
        self.string_options: dict[str, customtkinter.CTkTextbox] = {}
        self.choose_options: dict[str, customtkinter.CTkOptionMenu] = {}
        self.bool_options: dict[str, customtkinter.CTkCheckBox] = {}
        self.list_options: dict[str, list[customtkinter.CTkTextbox]] = {}
        self.date_time_options: dict[str, customtkinter.CTkTextbox] = {}
        self.date_and_time_pickers: dict[str, DateAndTimePickerWindow] = {}

    def get_config(self) -> dict[str, Any]:
        config: dict[str, Any] = {}
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

        for name, picker in self.date_time_options.items():
            config[name] = picker.get("0.0", "end").strip()

        return config


class SourceTab(OptionFrame):
    def __init__(
        self, parent: customtkinter.CTkFrame, source_name: str, config: dict[str, Any]
    ) -> None:
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
    def __init__(
        self,
        parent: customtkinter.CTkFrame,
        config: dict[str, Any],
        callback: Callable[..., None],
    ) -> None:
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
        self.add_date_time_option("last_song", "Time of last song", config["last_song"])
        self.add_string_option("preview_duration", "Preview Duration", config["preview_duration"])

    def get_config(self) -> dict[str, Any]:
        config = super().get_config()
        try:
            config["preview_duration"] = int(config["preview_duration"])
        except ValueError:
            config["preview_duration"] = 0

        return config


class SyngGui(customtkinter.CTk):  # type:ignore
    def on_close(self) -> None:
        if self.syng_server is not None:
            self.syng_server.kill()
            self.syng_server.join()

        if self.syng_client is not None:
            self.syng_client.terminate()
            self.syng_client.join()

        self.withdraw()
        self.destroy()

    def __init__(self) -> None:
        super().__init__(className="Syng")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        rel_path = os.path.dirname(__file__)
        img = ImageTk.PhotoImage(file=os.path.join(rel_path, "static/syng.png"))
        self.wm_iconbitmap()
        self.iconphoto(False, img)

        self.syng_server: Optional[Process] = None
        self.syng_client: Optional[Process] = None

        self.configfile = os.path.join(platformdirs.user_config_dir("syng"), "config.yaml")

        try:
            with open(self.configfile, encoding="utf8") as cfile:
                loaded_config = load(cfile, Loader=Loader)
        except FileNotFoundError:
            print("No config found, using default values")
            loaded_config = {}
        config: dict[str, dict[str, Any]] = {"sources": {}, "config": default_config()}

        try:
            config["config"] |= loaded_config["config"]
        except (KeyError, TypeError):
            print("Could not load config")

        # if "config" in loaded_config:
        #     config["config"] |= loaded_config["config"]

        if not config["config"]["secret"]:
            config["config"]["secret"] = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(8)
            )

        self.wm_title("Syng")

        # Buttons
        button_line = customtkinter.CTkFrame(self)
        button_line.pack(side="bottom", fill="x")

        startsyng_serverbutton = customtkinter.CTkButton(
            button_line, text="Start Local Server", command=self.start_syng_server
        )
        startsyng_serverbutton.pack(side="left", expand=True, anchor="w", padx=10, pady=5)

        savebutton = customtkinter.CTkButton(button_line, text="Save", command=self.save_config)
        savebutton.pack(side="left", padx=10, pady=5)

        # open_web_button = customtkinter.CTkButton(
        #     button_line, text="Open Web", command=self.open_web
        # )
        # open_web_button.pack(side="left", pady=5)

        self.startbutton = customtkinter.CTkButton(
            button_line, text="Save and Start", command=self.start_syng_client
        )
        self.startbutton.pack(side="left", padx=10, pady=10)

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
        self.qrlabel.pack(side="top", anchor="n", padx=10, pady=10)
        self.linklabel = customtkinter.CTkLabel(frm, text="")
        self.linklabel.bind("<Button-1>", lambda _: self.open_web())
        self.linklabel.pack()

        self.general_config = GeneralConfig(
            tabview.tab("General"), config["config"], self.update_qr
        )
        self.general_config.pack(ipadx=10, fill="both", expand=True)

        self.tabs = {}

        for source_name in available_sources:
            try:
                source_config = loaded_config["sources"][source_name]
            except (KeyError, TypeError):
                source_config = {}

            self.tabs[source_name] = SourceTab(tabview.tab(source_name), source_name, source_config)
            self.tabs[source_name].pack(ipadx=10, expand=True, fill="both")

        self.update_qr()

    def save_config(self) -> None:
        os.makedirs(os.path.dirname(self.configfile))

        with open(self.configfile, "w", encoding="utf-8") as f:
            dump(self.gather_config(), f, Dumper=Dumper)

    def gather_config(self) -> dict[str, Any]:
        sources = {}
        for source, tab in self.tabs.items():
            sources[source] = tab.get_config()

        general_config = self.general_config.get_config()

        return {"sources": sources, "config": general_config}

    def start_syng_client(self) -> None:
        if self.syng_client is None:
            self.save_config()
            config = self.gather_config()
            self.syng_client = multiprocessing.Process(
                target=create_async_and_start_client, args=(config,)
            )
            self.syng_client.start()
            self.startbutton.configure(text="Stop")
        else:
            self.syng_client.terminate()
            self.syng_client.join()
            self.syng_client = None
            self.startbutton.configure(text="Save and Start")

    def start_syng_server(self) -> None:
        self.syng_server = multiprocessing.Process(target=server_main)
        self.syng_server.start()

    def open_web(self) -> None:
        config = self.general_config.get_config()
        syng_server = config["server"]
        syng_server += "" if syng_server.endswith("/") else "/"
        room = config["room"]
        webbrowser.open(syng_server + room)

    def change_qr(self, data: str) -> None:
        qr = QRCode(box_size=20, border=2)
        qr.add_data(data)
        qr.make()
        image = qr.make_image().convert("RGB")
        tk_qrcode = customtkinter.CTkImage(light_image=image, size=(280, 280))
        self.qrlabel.configure(image=tk_qrcode)

    def update_qr(self, _evt: None = None) -> None:
        config = self.general_config.get_config()
        syng_server = config["server"]
        syng_server += "" if syng_server.endswith("/") else "/"
        room = config["room"]
        self.linklabel.configure(text=syng_server + room)
        self.change_qr(syng_server + room)


def main() -> None:
    SyngGui().mainloop()


if __name__ == "__main__":
    main()

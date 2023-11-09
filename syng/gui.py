import builtins
from json import load
import customtkinter
import qrcode
import secrets
import string
from tkinter import filedialog

from syng.client import default_config

from .sources import available_sources


class OptionFrame(customtkinter.CTkFrame):
    def add_option_label(self, text):
        customtkinter.CTkLabel(self, text=text, justify="left").grid(
            column=0, row=self.number_of_options, padx=5, pady=5
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
        self.bool_options[name].grid(column=1, row=self.number_of_options)
        self.number_of_options += 1

    def add_string_option(self, name, description, value="", callback=None):
        self.add_option_label(description)
        if value is None:
            value = ""

        self.string_options[name] = customtkinter.CTkTextbox(
            self, wrap="none", height=1
        )
        self.string_options[name].grid(column=1, row=self.number_of_options)
        self.string_options[name].insert("0.0", value)
        if callback is not None:
            self.string_options[name].bind("<KeyRelease>", callback)
            self.string_options[name].bind("<ButtonRelease>", callback)
        self.number_of_options += 1

    def add_list_option(self, name, description, value=[], callback=None):
        self.add_option_label(description)

        self.list_options[name] = customtkinter.CTkTextbox(self, wrap="none", height=1)
        self.list_options[name].grid(column=1, row=self.number_of_options)
        self.list_options[name].insert("0.0", ", ".join(value))
        if callback is not None:
            self.list_options[name].bind("<KeyRelease>", callback)
            self.list_options[name].bind("<ButtonRelease>", callback)
        self.number_of_options += 1

    def add_choose_option(self, name, description, values, value=""):
        self.add_option_label(description)
        self.choose_options[name] = customtkinter.CTkOptionMenu(self, values=values)
        self.choose_options[name].grid(column=1, row=self.number_of_options)
        self.choose_options[name].set(value)
        self.number_of_options += 1

    def __init__(self, parent):
        super().__init__(parent)
        self.number_of_options = 0
        self.string_options = {}
        self.choose_options = {}
        self.bool_options = {}
        self.list_options = {}

    def get_config(self):
        config = {}
        for name, textbox in self.string_options.items():
            config[name] = textbox.get("0.0", "end").strip()

        for name, optionmenu in self.choose_options.items():
            config[name] = optionmenu.get().strip()

        for name, checkbox in self.bool_options.items():
            config[name] = checkbox.get() == 1

        for name, textbox in self.list_options.items():
            config[name] = [
                v.strip() for v in textbox.get("0.0", "end").strip().split(",")
            ]

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
        for row, (name, (typ, desc, default)) in enumerate(
            source.config_schema.items()
        ):
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
            config["waiting_room_policy"],
        )
        self.add_string_option("last_song", "Time of last song", config["last_song"])
        self.add_string_option(
            "preview_duration", "Preview Duration", config["preview_duration"]
        )

        for name, textbox in self.string_options.items():
            if config[name]:
                textbox.insert("0.0", config[name])

        for name, optionmenu in self.choose_options.items():
            optionmenu.set(str(config[name]).lower())

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

    def __init__(self):
        super().__init__(className="Syng")

        with open("syng-client.json") as cfile:
            loaded_config = load(cfile)
        config = {"sources": {}, "config": default_config()}
        if "config" in loaded_config:
            config["config"] |= loaded_config["config"]

        if not config["config"]["secret"]:
            config["config"]["secret"] = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(8)
            )

        self.wm_title("Syng")

        fileframe = customtkinter.CTkFrame(self)
        fileframe.pack(side="bottom")

        loadbutton = customtkinter.CTkButton(
            fileframe,
            text="load",
            command=self.loadConfig,
        )
        loadbutton.pack(side="left")

        startbutton = customtkinter.CTkButton(
            fileframe, text="Start", command=self.start
        )
        startbutton.pack(side="right")

        frm = customtkinter.CTkFrame(self)
        frm.pack(ipadx=10, padx=10, fill="both", expand=True)

        tabview = customtkinter.CTkTabview(frm)
        tabview.pack(side="right", padx=10, pady=10, fill="both", expand=True)

        tabview.add("General")
        for source in available_sources:
            tabview.add(source)
        tabview.set("General")

        self.qrlabel = customtkinter.CTkLabel(frm, text="")
        self.qrlabel.pack(side="left")

        self.general_config = GeneralConfig(
            tabview.tab("General"), config["config"], self.updateQr
        )
        self.general_config.pack(ipadx=10, fill="y")

        self.tabs = {}

        for source_name in available_sources:
            try:
                source_config = loaded_config["sources"][source_name]
            except KeyError:
                source_config = {}

            self.tabs[source_name] = SourceTab(
                tabview.tab(source_name), source_name, source_config
            )
            self.tabs[source_name].pack(ipadx=10)

        self.updateQr()

    def start(self):
        sources = {}
        for source, tab in self.tabs.items():
            sources[source] = tab.get_config()

        general_config = self.general_config.get_config()

        config = {"sources": sources, "config": general_config}
        print(config)

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

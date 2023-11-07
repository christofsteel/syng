import builtins
from functools import partial
from json import load
import customtkinter
import qrcode
import secrets
import string
from tkinter import filedialog

from syng.client import default_config

from .sources import available_sources


class SourceTab(customtkinter.CTkFrame):
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
            self.vars[name] = value
            label = customtkinter.CTkLabel(self, text=f"{desc} ({name})")
            label.grid(column=0, row=row)
            match typ:
                case builtins.bool:
                    checkbox = customtkinter.CTkCheckBox(
                        self,
                        text="",
                        onvalue=True,
                        offvalue=False,
                    )
                    checkbox.bind(
                        "<ButtonRelease>", partial(self.updateBoolVar, name, checkbox)
                    )
                    checkbox.bind(
                        "<KeyRelease>", partial(self.updateBoolVar, name, checkbox)
                    )
                    if value:
                        checkbox.select()
                    else:
                        checkbox.deselect()
                    checkbox.grid(column=1, row=row)
                case builtins.list:
                    inputfield = customtkinter.CTkTextbox(self, wrap="none", height=1)
                    inputfield.bind(
                        "<KeyRelease>", partial(self.updateStrVar, name, inputfield)
                    )
                    inputfield.bind(
                        "<ButtonRelease>", partial(self.updateStrVar, name, inputfield)
                    )
                    inputfield.insert("0.0", ", ".join(value))
                    inputfield.grid(column=1, row=row)
                case builtins.str:
                    inputfield = customtkinter.CTkTextbox(self, wrap="none", height=1)
                    inputfield.bind(
                        "<KeyRelease>", partial(self.updateStrVar, name, inputfield)
                    )
                    inputfield.bind(
                        "<ButtonRelease>", partial(self.updateStrVar, name, inputfield)
                    )
                    inputfield.insert("0.0", value)
                    inputfield.grid(column=1, row=row)

    def get_config(self):
        return self.vars


class GeneralConfig(customtkinter.CTkFrame):
    def add_option_label(self, text):
        customtkinter.CTkLabel(self, text=text, justify="left").grid(
            column=0, row=self.number_of_options, padx=5, pady=5
        )

    def add_string_option(self, name, description, callback=None):
        self.add_option_label(description)

        self.string_options[name] = customtkinter.CTkTextbox(
            self, wrap="none", height=1
        )
        self.string_options[name].grid(column=1, row=self.number_of_options)
        if callback is not None:
            self.string_options[name].bind("<KeyRelease>", callback)
        self.number_of_options += 1

    def add_choose_option(self, name, description, values):
        self.add_option_label(description)
        self.choose_options[name] = customtkinter.CTkOptionMenu(self, values=values)
        self.choose_options[name].grid(column=1, row=self.number_of_options)
        self.number_of_options += 1

    def __init__(self, parent, config, callback):
        super().__init__(parent)
        self.number_of_options = 0
        self.string_options = {}
        self.choose_options = {}

        self.add_string_option("server", "Server", callback)
        self.add_string_option("room", "Room", callback)
        self.add_string_option("secret", "Secret")
        self.add_choose_option(
            "waiting_room_policy", "Waiting room policy", ["forced", "optional", "none"]
        )
        self.add_string_option("last_song", "Time of last song")
        self.add_string_option("preview_duration", "Preview Duration")

        for name, textbox in self.string_options.items():
            if config[name]:
                textbox.insert("0.0", config[name])

        for name, optionmenu in self.choose_options.items():
            optionmenu.set(str(config[name]).lower())

    def get_config(self):
        config = {}
        for name, textbox in self.string_options.items():
            config[name] = textbox.get("0.0", "end").strip()

        for name, optionmenu in self.choose_options.items():
            config[name] = optionmenu.get().strip()

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
        tabview = customtkinter.CTkTabview(self)
        tabview.pack(side="top")

        tabview.add("General")
        for source in available_sources:
            tabview.add(source)
        tabview.set("General")

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

        frm = customtkinter.CTkFrame(tabview.tab("General"))
        frm.grid(ipadx=10)

        self.qrlabel = customtkinter.CTkLabel(frm, text="")
        self.qrlabel.grid(column=0, row=0)

        self.general_config = GeneralConfig(frm, config["config"], self.updateQr)
        self.general_config.grid(column=1, row=0)

        self.tabs = {}

        for source_name in available_sources:
            try:
                source_config = loaded_config["sources"][source_name]
            except KeyError:
                source_config = {}

            self.tabs[source_name] = SourceTab(
                tabview.tab(source_name), source_name, source_config
            )
            self.tabs[source_name].grid(ipadx=10)

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

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
    def __init__(self, parent, config, callback):
        super().__init__(parent)
        customtkinter.CTkLabel(self, text="Server", justify="left").grid(
            column=0, row=0, padx=5, pady=5
        )
        self.serverTextbox = customtkinter.CTkTextbox(self, wrap="none", height=1)
        self.serverTextbox.grid(column=1, row=0)
        self.serverTextbox.bind("<KeyRelease>", callback)

        customtkinter.CTkLabel(self, text="Room", justify="left").grid(column=0, row=1)
        self.roomTextbox = customtkinter.CTkTextbox(self, wrap="none", height=1)
        self.roomTextbox.grid(column=1, row=1)
        self.roomTextbox.bind("<KeyRelease>", callback)

        customtkinter.CTkLabel(self, text="Secret", justify="left").grid(
            column=0, row=3
        )
        self.secretTextbox = customtkinter.CTkTextbox(self, wrap="none", height=1)

        secret = "".join(
            secrets.choice(string.ascii_letters + string.digits) for _ in range(8)
        )

        self.secretTextbox.grid(column=1, row=3)

        customtkinter.CTkLabel(self, text="Waiting room policy", justify="left").grid(
            column=0, row=4
        )
        self.waitingRoomPolicy = customtkinter.CTkOptionMenu(
            self, values=["forced", "optional", "none"]
        )
        self.waitingRoomPolicy.set("none")
        self.waitingRoomPolicy.grid(column=1, row=4)

        customtkinter.CTkLabel(self, text="Time of last Song", justify="left").grid(
            column=0, row=5
        )
        self.last_song = customtkinter.CTkTextbox(self, wrap="none", height=1)
        self.last_song.grid(column=1, row=5)

        customtkinter.CTkLabel(self, text="Preview Duration", justify="left").grid(
            column=0, row=6
        )
        self.preview_duration = customtkinter.CTkTextbox(self, wrap="none", height=1)
        self.preview_duration.grid(column=1, row=6)

        self.serverTextbox.insert("0.0", config["server"])
        self.roomTextbox.insert("0.0", config["room"])
        self.secretTextbox.insert(
            "0.0", config["secret"] if "secret" in config else secret
        )
        self.waitingRoomPolicy.set(str(config["waiting_room_policy"]).lower())
        if config["last_song"]:
            self.last_song.insert("0.0", config["last_song"])
        self.preview_duration.insert("0.0", config["preview_duration"])

    def get_config(self):
        config = {}
        config["server"] = self.serverTextbox.get("0.0", "end").strip()
        config["room"] = self.roomTextbox.get("0.0", "end").strip()
        config["secret"] = self.secretTextbox.get("0.0", "end").strip()
        config["waiting_room_policy"] = self.waitingRoomPolicy.get().strip()
        config["last_song"] = self.last_song.get("0.0", "end").strip()
        try:
            config["preview_duration"] = int(
                self.preview_duration.get("0.0", "end").strip()
            )
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
        config = {"sources": {}, "config": {}}
        if "config" in loaded_config:
            config["config"] = default_config() | loaded_config["config"]

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

        startbutton = customtkinter.CTkButton(self, text="Start", command=self.start)
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

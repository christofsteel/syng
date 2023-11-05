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


class SyngGui(customtkinter.CTk):
    def loadConfig(self):
        filedialog.askopenfilename()

    def __init__(self):
        super().__init__(className="Syng")

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

        frm = customtkinter.CTkFrame(tabview.tab("General"))
        frm.grid(ipadx=10)

        self.qrlabel = customtkinter.CTkLabel(frm, text="")
        self.qrlabel.grid(column=0, row=0)

        optionframe = customtkinter.CTkFrame(frm)
        optionframe.grid(column=1, row=0)

        customtkinter.CTkLabel(optionframe, text="Server", justify="left").grid(
            column=0, row=0, padx=5, pady=5
        )
        self.serverTextbox = customtkinter.CTkTextbox(
            optionframe, wrap="none", height=1
        )
        self.serverTextbox.grid(column=1, row=0)
        self.serverTextbox.bind("<KeyRelease>", self.updateQr)

        customtkinter.CTkLabel(optionframe, text="Room", justify="left").grid(
            column=0, row=1
        )
        self.roomTextbox = customtkinter.CTkTextbox(optionframe, wrap="none", height=1)
        self.roomTextbox.grid(column=1, row=1)
        self.roomTextbox.bind("<KeyRelease>", self.updateQr)

        customtkinter.CTkLabel(optionframe, text="Secret", justify="left").grid(
            column=0, row=3
        )
        self.secretTextbox = customtkinter.CTkTextbox(
            optionframe, wrap="none", height=1
        )
        secret = "".join(
            secrets.choice(string.ascii_letters + string.digits) for _ in range(8)
        )
        self.secretTextbox.grid(column=1, row=3)

        customtkinter.CTkLabel(
            optionframe, text="Waiting room policy", justify="left"
        ).grid(column=0, row=4)
        self.waitingRoomPolicy = customtkinter.CTkOptionMenu(
            optionframe, values=["forced", "optional", "none"]
        )
        self.waitingRoomPolicy.set("none")
        self.waitingRoomPolicy.grid(column=1, row=4)

        customtkinter.CTkLabel(
            optionframe, text="Time of last Song", justify="left"
        ).grid(column=0, row=5)
        self.last_song = customtkinter.CTkTextbox(optionframe, wrap="none", height=1)
        self.last_song.grid(column=1, row=5)

        customtkinter.CTkLabel(
            optionframe, text="Preview Duration", justify="left"
        ).grid(column=0, row=6)
        self.preview_duration = customtkinter.CTkTextbox(
            optionframe, wrap="none", height=1
        )
        self.preview_duration.grid(column=1, row=6)

        customtkinter.CTkButton(optionframe, text="Start", command=self.start).grid(
            column=0, row=7, columnspan=2, pady=10
        )

        with open("syng-client.json") as cfile:
            loaded_config = load(cfile)
        config = {"sources": {}, "config": {}}

        self.source_config_elements = {}
        for source_name, source in available_sources.items():
            self.source_config_elements[source_name] = {}
            config["sources"][source_name] = {}
            sourcefrm = customtkinter.CTkFrame(tabview.tab(source_name))
            sourcefrm.grid(ipadx=10)
            for row, (name, (typ, desc, default)) in enumerate(
                source.config_schema.items()
            ):
                if name in loaded_config["sources"][source_name]:
                    config["sources"][source_name][name] = loaded_config["sources"][
                        source_name
                    ][name]
                else:
                    config["sources"][source_name][name] = default

                label = customtkinter.CTkLabel(
                    sourcefrm, text=f"{desc} ({name})", justify="right"
                )
                label.grid(column=0, row=row)
                match typ:
                    case builtins.bool:
                        self.source_config_elements[source_name][
                            name
                        ] = customtkinter.CTkSwitch(sourcefrm, text="")
                        self.source_config_elements[source_name][name].grid(
                            column=1, row=row
                        )
                        if config["sources"][source_name][name]:
                            self.source_config_elements[source_name][name].select()
                        else:
                            self.source_config_elements[source_name][name].deselect()

                    case builtins.list:
                        self.source_config_elements[source_name][
                            name
                        ] = customtkinter.CTkTextbox(sourcefrm, wrap="none", height=1)
                        self.source_config_elements[source_name][name].grid(
                            column=1, row=row
                        )
                        self.source_config_elements[source_name][name].insert(
                            "0.0", ",".join(config["sources"][source_name][name])
                        )

                    case _:
                        self.source_config_elements[source_name][
                            name
                        ] = customtkinter.CTkTextbox(sourcefrm, wrap="none", height=1)
                        self.source_config_elements[source_name][name].grid(
                            column=1, row=row
                        )
                        self.source_config_elements[source_name][name].insert(
                            "0.0", config["sources"][source_name][name]
                        )
            if source_name in loaded_config["sources"]:
                config["sources"][source_name] |= loaded_config["sources"][source_name]

        if "config" in loaded_config:
            config["config"] = default_config() | loaded_config["config"]

        self.serverTextbox.insert("0.0", config["config"]["server"])
        self.roomTextbox.insert("0.0", config["config"]["room"])
        self.secretTextbox.insert("0.0", config["config"]["secret"])
        self.waitingRoomPolicy.set(str(config["config"]["waiting_room_policy"]).lower())
        if config["config"]["last_song"]:
            self.last_song.insert("0.0", config["config"]["last_song"])
        self.preview_duration.insert("0.0", config["config"]["preview_duration"])

        self.updateQr()

    def start(self):
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

        sources = {}
        for source_name, config_elements in self.source_config_elements.items():
            sources[source_name] = {}
            for option, config_element in config_elements.items():
                if isinstance(config_element, customtkinter.CTkSwitch):
                    sources[source_name][option] = (
                        True if config_element.get() == 1 else False
                    )
                elif isinstance(config_element, customtkinter.CTkTextbox):
                    match available_sources[source_name].config_schema[option][0]:
                        case builtins.list:
                            sources[source_name][option] = [
                                value.strip()
                                for value in config_element.get("0.0", "end")
                                .strip()
                                .split(",")
                            ]

                        case builtins.str:
                            sources[source_name][option] = config_element.get(
                                "0.0", "end"
                            ).strip()
                else:
                    raise RuntimeError("IDK")

        syng_config = {"sources": sources, "config": config}

        print(syng_config)

    def changeQr(self, data: str):
        qr = qrcode.QRCode(box_size=20, border=2)
        qr.add_data(data)
        qr.make()
        qr.print_ascii()
        image = qr.make_image().convert("RGB")
        tkQrcode = customtkinter.CTkImage(light_image=image, size=(280, 280))
        self.qrlabel.configure(image=tkQrcode)

    def updateQr(self, _evt=None):
        server = self.serverTextbox.get("0.0", "end").strip()
        server += "" if server.endswith("/") else "/"
        room = self.roomTextbox.get("0.0", "end").strip()
        print(server + room)
        self.changeQr(server + room)


def main():
    SyngGui().mainloop()


if __name__ == "__main__":
    main()

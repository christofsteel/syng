from typing import Any

from PySide6.QtCore import QResource
from PySide6.QtGui import QIcon, QImage, QPalette, QPixmap


def colorize_icon(resource_path: str, palette: QPalette) -> QIcon:
    """Colorize an svg icon from a resource.

    Since Qt6 does not implement `currentColor`, we need to change the color of some icons
    manually for light/dark mode, by replacing currentColor with another color.

    By default, it is colored as the default button text color.

    Args:
        resource_path: The resource path of the svg
        palette: palette from which to take the text color

    Returns:
        A QIcon with the svg rendered in the specified color.
    """
    color = palette.color(QPalette.ColorRole.ButtonText).name()
    resource_data: Any = QResource(resource_path).data()
    colored_svg_data = resource_data.tobytes().replace(b"currentColor", color.encode())
    return QIcon(QPixmap.fromImage(QImage.fromData(colored_svg_data)))

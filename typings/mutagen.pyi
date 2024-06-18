class Info:
    length: int

class File:
    def __init__(self, filename: str): ...
    info: Info

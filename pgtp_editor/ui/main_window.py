from PySide6.QtWidgets import QMainWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PGTP Editor")
        self.resize(1400, 900)

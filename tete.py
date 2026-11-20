import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget


class JojoJanela(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        # Configurações da janela
        self.setWindowTitle("JOJO-OS v4.0 // PyQt6 Edition")
        self.setGeometry(100, 100, 400, 300)
        
        # Estilo visual usando QSS (é como se fosse o CSS do PyQt)
        self.setStyleSheet("background-color: #000000;")

        # Criando elementos (Widgets)
        self.label = QLabel("⭐ BIZARRE ADVENTURE", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("color: #FFD60A; font-family: Impact; font-size: 24px;")

        self.btn = QPushButton("🔄 ALTERAR SKIN", self)
        self.btn.setStyleSheet("""
            QPushButton {
                background-color: #5E60CE; 
                color: #FFD60A; 
                font-family: Impact; 
                font-size: 14px;
                border: 2px solid #FFD60A;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #7400B8;
            }
        """)

        # Organizando os elementos na tela
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.btn)
        self.setLayout(layout)

# Código para fazer a janela rodar
if __name__ == "__main__":
    app = QApplication(sys.argv)
    janela = JojoJanela()
    janela.show()
    sys.exit(app.exec())
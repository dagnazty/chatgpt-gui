# main.py

import sys
from PyQt5.QtWidgets import QApplication
from gui import ChatGPTGUI

def main():
    app = QApplication(sys.argv)
    window = ChatGPTGUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

# main_gui.py

import json
import logging
import os
import threading
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from PyQt5.QtCore import QObject, QSize, Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QColor, QFont, QIcon, QTextCursor, QTextCharFormat
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QFrame,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from chatgpt_handler import ChatGPTHandler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()


class Communicate(QObject):
    """Communication class for sending signals between threads and the GUI."""
    append_chat_signal = pyqtSignal(str, str)  # sender, message
    update_send_button_signal = pyqtSignal(bool, str)  # enabled, text


class ChatMessageWidget(QWidget):
    """Custom widget to display chat messages with formatting."""

    def __init__(
        self,
        sender: str,
        message: str,
        timestamp: Optional[datetime] = None,
        parent: Optional[QWidget] = None,
    ):
        """Initialize the chat message widget.

        Args:
            sender (str): The sender of the message.
            message (str): The message content.
            timestamp (Optional[datetime]): The time the message was sent. Defaults to current time.
            parent (Optional[QWidget]): The parent widget.
        """
        super().__init__(parent)
        self.sender = sender
        self.message = message
        self.timestamp = timestamp or datetime.now()
        self.init_ui()

    def init_ui(self) -> None:
        """Set up the UI elements."""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(5)

        timestamp_str = self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        sender_label = QLabel(f"{self.sender} [{timestamp_str}]:")
        sender_label.setStyleSheet("font-weight: bold; color: #555555;")

        message_text = QTextEdit()
        message_text.setReadOnly(True)
        message_text.setFrameStyle(QFrame.NoFrame)
        message_text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        message_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        message_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        message_text.setWordWrapMode(1)  # Enable word wrap

        if self.sender == "You":
            background_color = "#E8F5E9"  # Light green
            alignment = Qt.AlignRight
        else:
            background_color = "#FFFFFF"  # White
            alignment = Qt.AlignLeft

        message_text.setStyleSheet(f"background-color: {background_color}; border: none;")

        self.set_message_content(message_text, self.message)

        layout.addWidget(sender_label)
        layout.addWidget(message_text)
        layout.setAlignment(alignment)
        self.setLayout(layout)

        message_text.adjustSize()
        self.adjustSize()

    def set_message_content(self, message_text_edit: QTextEdit, content: str) -> None:
        """Set the content of the message in the text edit widget.
        Handles code blocks denoted by triple backticks.

        Args:
            message_text_edit (QTextEdit): The text edit widget to set content on.
            content (str): The message content.
        """
        message_text_edit.clear()
        cursor = message_text_edit.textCursor()

        if '```' in content:
            parts = content.split('```')
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    # Regular text
                    fmt = QTextCharFormat()
                    fmt.setFont(QFont("Segoe UI", 10))
                    fmt.setBackground(QColor("transparent"))
                    cursor.insertText(part, fmt)
                else:
                    # Code block
                    code = part.strip()
                    fmt = QTextCharFormat()
                    fmt.setFont(QFont("Consolas", 10))
                    fmt.setBackground(QColor("#F5F5F5"))
                    cursor.insertText(code + '\n', fmt)
            message_text_edit.setAlignment(Qt.AlignLeft)
        else:
            fmt = QTextCharFormat()
            fmt.setFont(QFont("Segoe UI", 10))
            cursor.insertText(content, fmt)

        message_text_edit.moveCursor(QTextCursor.Start)

    def sizeHint(self) -> QSize:
        """Override sizeHint to return the size of the layout."""
        return self.layout().sizeHint()


class ChatGPTGUI(QMainWindow):
    """Main window class for the ChatGPT GUI application."""

    def __init__(self):
        """Initialize the ChatGPT GUI."""
        super().__init__()
        self.setWindowTitle("ChatGPT GUI")
        self.setGeometry(100, 100, 800, 600)
        self.chatgpt = ChatGPTHandler(rate_limit_max_calls=60, rate_limit_period=60.0)  # Set your rate limits here
        self.comm = Communicate()
        self.comm.append_chat_signal.connect(self.append_chat)
        self.comm.update_send_button_signal.connect(self.update_send_button)

        # Create a session file on launch
        self.session_file_path = self.create_session_file()

        self.init_ui()

        self.comm.append_chat_signal.emit(
            "ChatGPT", "Hello! I'm ChatGPT. How can I assist you today?"
        )

    def init_ui(self) -> None:
        """Set up the UI elements."""
        # Apply a custom stylesheet to the application
        style_sheet = """
        QMainWindow {
            background-color: #F0F0F0;
        }

        QTextEdit {
            background-color: #FFFFFF;
            border: 1px solid #CCCCCC;
            border-radius: 5px;
        }

        QPushButton {
            background-color: #4CAF50;
            color: white;
            font-weight: bold;
            border-radius: 5px;
            padding: 10px;
        }

        QPushButton:hover {
            background-color: #45A049;
        }

        QPushButton:disabled {
            background-color: #A5D6A7;
            color: #FFFFFF;
        }

        QLabel {
            color: #333333;
        }

        QScrollArea {
            border: none;
        }
        """

        self.setStyleSheet(style_sheet)

        # Menu bar setup
        menubar = self.menuBar()
        file_menu = menubar.addMenu('File')

        save_session_action = QAction('Save Session', self)
        save_session_action.triggered.connect(self.save_session)
        file_menu.addAction(save_session_action)

        load_session_action = QAction('Load Session', self)
        load_session_action.triggered.connect(self.load_session)
        file_menu.addAction(load_session_action)

        export_chat_action = QAction('Export Chat as Markdown', self)
        export_chat_action.triggered.connect(self.export_chat_as_markdown)
        file_menu.addAction(export_chat_action)

        file_menu.addSeparator()

        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = menubar.addMenu('Help')
        about_action = QAction('About', self)
        about_action.triggered.connect(self.about)
        help_menu.addAction(about_action)

        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # Splitter to adjust chat and input areas
        splitter = QSplitter(Qt.Vertical)

        # Chat area
        self.chat_area = QWidget()
        self.chat_layout = QVBoxLayout()
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_area.setLayout(self.chat_layout)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setWidget(self.chat_area)
        splitter.addWidget(self.chat_scroll)

        # Input area
        input_widget = QWidget()
        input_layout = QVBoxLayout()
        input_layout.setContentsMargins(10, 10, 10, 10)
        input_layout.setSpacing(5)
        input_widget.setLayout(input_layout)

        self.input_field = QTextEdit()
        self.input_field.setFont(QFont("Segoe UI", 12))
        self.input_field.setPlaceholderText("Type your message or paste your code here...")
        input_layout.addWidget(self.input_field)

        self.send_button = QPushButton("Send")
        self.send_button.setFixedWidth(100)
        self.send_button.setFixedHeight(40)
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button, alignment=Qt.AlignRight)

        splitter.addWidget(input_widget)

        # Set initial splitter sizes
        splitter.setSizes([int(self.height() * 0.6), int(self.height() * 0.4)])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        main_layout.addWidget(splitter)

        # Initialize the system tray icon
        icon_path = os.path.join(os.path.dirname(__file__), "icons", "icon.ico")
        if os.path.exists(icon_path):
            app_icon = QIcon(icon_path)
        else:
            app_icon = QIcon.fromTheme("application-default-icon")

        self.setWindowIcon(app_icon)
        self.tray_icon = QSystemTrayIcon(app_icon, self)
        self.tray_icon.setIcon(app_icon)

        # Create the tray icon menu
        tray_menu = QMenu()

        restore_action = QAction("Restore", self)
        restore_action.triggered.connect(self.showNormal)
        tray_menu.addAction(restore_action)

        tray_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

        # Handle tray icon activation
        self.tray_icon.activated.connect(self.on_tray_icon_activated)

    def create_session_file(self) -> str:
        """Create a new session file and return its file path."""
        sessions_dir = "sessions"
        os.makedirs(sessions_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_file_path = os.path.join(sessions_dir, f"session_{timestamp}.json")
        # Initialize the session file with empty data
        session_data = self.chatgpt.get_session_data()
        with open(session_file_path, 'w', encoding='utf-8') as file:
            json.dump(session_data, file, ensure_ascii=False, indent=4)
        logger.info(f"Session file created at {session_file_path}")
        return session_file_path

    def send_message(self) -> None:
        """Handle the send button click event by sending the user's message."""
        user_input = self.input_field.toPlainText().strip()
        if not user_input:
            return

        self.comm.append_chat_signal.emit("You", user_input)
        self.input_field.clear()
        # Disable the send button and change its text
        self.send_button.setEnabled(False)
        self.send_button.setText("Sending...")
        threading.Thread(target=self.process_message, args=(user_input,), daemon=True).start()

    def process_message(self, user_input: str) -> None:
        """Process the user's message by sending it to ChatGPT and handling the response.

        Args:
            user_input (str): The user's message input.
        """
        try:
            response = self.chatgpt.send_message(user_input)
            if response:
                self.comm.append_chat_signal.emit("ChatGPT", response)
            else:
                self.comm.append_chat_signal.emit("ChatGPT", "⚠️ No response received from ChatGPT.")
        except Exception as e:
            logger.error(f"Failed to get response: {e}")
            self.comm.append_chat_signal.emit("ChatGPT", f"⚠️ Error: {e}")
        finally:
            self.comm.update_send_button_signal.emit(True, "Send")

    def append_chat(self, sender: str, message: str) -> None:
        """Append a chat message to the chat area.

        Args:
            sender (str): The sender of the message.
            message (str): The message content.
        """
        timestamp = datetime.now()
        message_widget = ChatMessageWidget(sender, message, timestamp)
        self.chat_layout.addWidget(message_widget)
        QTimer.singleShot(
            100,
            lambda: self.chat_scroll.verticalScrollBar().setValue(
                self.chat_scroll.verticalScrollBar().maximum()
            ),
        )
        # Save the session after updating the chat
        self.save_session_to_file()

    def save_session_to_file(self) -> None:
        """Save the current session data to the session file."""
        try:
            session_data = self.chatgpt.get_session_data()
            with open(self.session_file_path, 'w', encoding='utf-8') as file:
                json.dump(session_data, file, ensure_ascii=False, indent=4)
            logger.info(f"Session saved to {self.session_file_path}")
        except Exception as e:
            logger.error(f"Failed to save session: {e}")

    def update_send_button(self, enabled: bool, text: str) -> None:
        """Update the send button's enabled state and text.

        Args:
            enabled (bool): Whether the button is enabled.
            text (str): The text to display on the button.
        """
        self.send_button.setEnabled(enabled)
        self.send_button.setText(text)

    def save_session(self) -> None:
        """Save the current chat session to a file."""
        session_name, _ = QFileDialog.getSaveFileName(
            self,
            "Save Session",
            os.path.join("sessions", f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"),
            "JSON Files (*.json)",
        )
        if session_name:
            try:
                session_data = self.chatgpt.get_session_data()
                with open(session_name, 'w', encoding='utf-8') as file:
                    json.dump(session_data, file, ensure_ascii=False, indent=4)
                QMessageBox.information(self, "Success", "Session saved successfully.")
                logger.info(f"Session saved to {session_name}")
            except Exception as e:
                logger.error(f"Failed to save session: {e}")
                QMessageBox.critical(self, "Error", f"Failed to save session:\n{e}")

    def load_session(self) -> None:
        """Load a chat session from a file."""
        session_path, _ = QFileDialog.getOpenFileName(
            self, "Load Session", "sessions/", "JSON Files (*.json)"
        )
        if session_path:
            try:
                with open(session_path, 'r', encoding='utf-8') as file:
                    session_data = json.load(file)
                self.chatgpt.load_session(session_data)
                # Clear current chat
                for i in reversed(range(self.chat_layout.count())):
                    widget = self.chat_layout.itemAt(i).widget()
                    if widget is not None:
                        widget.setParent(None)
                # Load messages from session
                for message in session_data.get("messages", []):
                    sender = "You" if message["role"] == "user" else "ChatGPT"
                    content = message.get("content", "")
                    # Assuming timestamps are stored; adjust if necessary
                    timestamp = datetime.now()
                    self.append_chat(sender, content)
                QMessageBox.information(self, "Success", "Session loaded successfully.")
                logger.info(f"Session loaded from {session_path}")
            except Exception as e:
                logger.error(f"Failed to load session: {e}")
                QMessageBox.critical(self, "Error", f"Failed to load session:\n{e}")

    def export_chat_as_markdown(self) -> None:
        """Export the chat history as a Markdown file."""
        export_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Chat as Markdown",
            os.path.join("exports", f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"),
            "Markdown Files (*.md)",
        )
        if export_path:
            try:
                session_data = self.chatgpt.get_session_data()
                with open(export_path, 'w', encoding='utf-8') as file:
                    for message in session_data.get("messages", []):
                        sender = "You" if message["role"] == "user" else "ChatGPT"
                        content = message.get("content", "")
                        file.write(f"**{sender}:**\n\n{content}\n\n---\n\n")
                QMessageBox.information(self, "Success", "Chat exported successfully.")
                logger.info(f"Chat exported to {export_path}")
            except Exception as e:
                logger.error(f"Failed to export chat: {e}")
                QMessageBox.critical(self, "Error", f"Failed to export chat:\n{e}")

    def about(self) -> None:
        """Display information about the application."""
        QMessageBox.information(
            self, "About", "ChatGPT GUI \n\nDeveloped with PyQt5 and OpenAI API.\n\nDeveloped by dagnazty"
        )

    def on_tray_icon_activated(self, reason):
        """Handle the tray icon activation."""
        if reason == QSystemTrayIcon.Trigger:  # Triggered by a left-click
            if self.isHidden():
                self.show()
                self.setWindowState(Qt.WindowActive)
            else:
                self.hide()


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    gui = ChatGPTGUI()
    gui.show()
    sys.exit(app.exec_())

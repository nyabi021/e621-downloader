import sys
import os
import asyncio
import aiohttp
import ssl
import base64
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QTextEdit, QFileDialog, QMessageBox, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt6.QtGui import QIntValidator
from pathlib import Path

class DownloaderThread(QThread):
    progress_signal = pyqtSignal(str)
    download_complete = pyqtSignal()
    error_signal = pyqtSignal(str)

    def __init__(self, settings_dict):
        super().__init__()
        self.settings_dict = settings_dict
        self.session = None
        self.running = True

    def encode_credentials(self, username, api_key):
        credentials = f"{username}:{api_key}"
        return base64.b64encode(credentials.encode()).decode()

    async def login(self):
        try:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            timeout = aiohttp.ClientTimeout(total=30)

            username = self.settings_dict['credentials']['username']
            api_key = self.settings_dict['credentials']['api_key']
            
            headers = {
                'User-Agent': 'PawLoad/1.0 (by {})'.format(username),
                'Authorization': f'Basic {self.encode_credentials(username, api_key)}'
            }
            
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            async with aiohttp.ClientSession(
                headers=headers, 
                connector=connector,
                timeout=timeout
            ) as session:
                self.progress_signal.emit(
                    f"Attempting to login as {self.settings_dict['credentials']['username']}"
                )
                try:
                    async with session.get('https://e621.net/posts.json?limit=1') as response:
                        if response.status == 200:
                            return True
                        elif response.status == 401:
                            self.error_signal.emit("Authentication failed. Please check your credentials.")
                            return False
                        else:
                            self.error_signal.emit(f"Server returned status code: {response.status}")
                            return False
                except aiohttp.ClientConnectorError as e:
                    self.error_signal.emit(f"Connection error: {str(e)}")
                    return False
                except asyncio.TimeoutError:
                    self.error_signal.emit("Connection timed out. Please check your internet connection.")
                    return False
        except Exception as e:
            self.error_signal.emit(f"Login error: {str(e)}")
            return False

    async def download_posts(self):
        try:
            if not await self.login():
                return

            headers = {
                'User-Agent': 'PawLoad/1.0'
            }
            auth = aiohttp.BasicAuth(
                login=self.settings_dict['credentials']['username'],
                password=self.settings_dict['credentials']['api_key']
            )

            async with aiohttp.ClientSession(auth=auth, headers=headers) as session:
                self.session = session
                tags = self.settings_dict['download']['tags']
                limit = self.settings_dict['download']['limit']
                save_dir = self.settings_dict['download']['save_directory']

                os.makedirs(save_dir, exist_ok=True)

                self.progress_signal.emit(f"Fetching posts with tags: {tags}")
                async with session.get(
                    'https://e621.net/posts.json',
                    params={'tags': tags, 'limit': limit}
                ) as response:
                    if response.status != 200:
                        self.error_signal.emit(f"API Error: {response.status}")
                        return
                    
                    data = await response.json()
                    posts = data.get('posts', [])
                    
                    if not posts:
                        self.progress_signal.emit("No posts found with given tags")
                        return

                    self.progress_signal.emit(f"Found {len(posts)} posts")
                    
                    for i, post in enumerate(posts):
                        if not self.running:
                            self.progress_signal.emit("\nDownload interrupted by user.")
                            return

                        url = post.get('file', {}).get('url')
                        if not url:
                            continue

                        post_id = post.get('id', 'unknown')
                        artists = post.get('tags', {}).get('artist', ['unknown'])
                        artist = artists[0] if artists else 'unknown'
                        ext = url.split('.')[-1]

                        filename = f"{artist}_{post_id}.{ext}"
                        filepath = os.path.join(save_dir, filename)

                        if os.path.exists(filepath):
                            self.progress_signal.emit(f"Skipping {filename} (already exists)")
                            continue

                        self.progress_signal.emit(f"Downloading {filename}")
                        try:
                            async with session.get(url) as img_response:
                                if img_response.status == 200:
                                    with open(filepath, 'wb') as f:
                                        f.write(await img_response.read())
                                    self.progress_signal.emit(f"Successfully downloaded {filename}")
                                else:
                                    self.progress_signal.emit(f"Failed to download {filename}")
                        except Exception as e:
                            self.progress_signal.emit(f"Error downloading {filename}: {str(e)}")

                        await asyncio.sleep(1)

            self.download_complete.emit()

        except Exception as e:
            self.error_signal.emit(f"Error during download: {str(e)}")

    def run(self):
        asyncio.run(self.download_posts())

    def stop(self):
        self.running = False

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PawLoad")
        self.setMinimumSize(600, 400)
        
        self.settings = QSettings('PawLoad', 'Settings')
        
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QLabel, QCheckBox {
                font-size: 12px;
                color: #333333;
            }
            QLineEdit {
                padding: 8px;
                border: 1px solid #cccccc;
                border-radius: 4px;
                background-color: white;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #66afe9;
            }
            QPushButton {
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                color: white;
                background-color: #007bff;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:pressed {
                background-color: #004085;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
            QPushButton#stopButton {
                background-color: #6c757d;
            }
            QPushButton#stopButton:hover {
                background-color: #5a6268;
            }
            QTextEdit {
                border: 1px solid #cccccc;
                border-radius: 4px;
                background-color: white;
                font-family: "Consolas", monospace;
                font-size: 12px;
                padding: 8px;
            }
        """)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        input_layout = QVBoxLayout()
        input_layout.setSpacing(10)
        
        # Username section
        username_layout = QVBoxLayout()
        username_label = QLabel("Username")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter your username")
        username_layout.addWidget(username_label)
        username_layout.addWidget(self.username_input)
        
        # API Key section
        apikey_layout = QVBoxLayout()
        apikey_label = QLabel("API Key")
        self.apikey_input = QLineEdit()
        self.apikey_input.setPlaceholderText("Enter your API key")
        self.apikey_input.setEchoMode(QLineEdit.EchoMode.Password)
        apikey_layout.addWidget(apikey_label)
        apikey_layout.addWidget(self.apikey_input)
        
        self.remember_me = QCheckBox("Remember Me")
        
        # Tags section
        tags_layout = QVBoxLayout()
        tags_label = QLabel("Tags")
        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("Enter tags (space separated)")
        tags_layout.addWidget(tags_label)
        tags_layout.addWidget(self.tags_input)

        # Limit section
        limit_layout = QVBoxLayout()
        limit_label = QLabel("Maximum Images")
        self.limit_input = QLineEdit()
        self.limit_input.setPlaceholderText("Enter maximum number of images (default: 320)")
        self.limit_input.setText("320")
        self.limit_input.setValidator(QIntValidator(1, 10000))
        limit_layout.addWidget(limit_label)
        limit_layout.addWidget(self.limit_input)
        
        # Directory section
        dir_layout = QVBoxLayout()
        dir_label = QLabel("Save Directory")
        dir_input_layout = QHBoxLayout()
        self.dir_input = QLineEdit()
        self.dir_input.setPlaceholderText("Select save directory")
        self.dir_button = QPushButton("Browse")
        self.dir_button.setObjectName("browseButton")
        self.dir_button.setStyleSheet("""
            QPushButton#browseButton {
                background-color: #6c757d;
            }
            QPushButton#browseButton:hover {
                background-color: #5a6268;
            }
        """)
        self.dir_button.clicked.connect(self.select_directory)
        dir_input_layout.addWidget(self.dir_input)
        dir_input_layout.addWidget(self.dir_button)
        dir_layout.addWidget(dir_label)
        dir_layout.addLayout(dir_input_layout)
        
        # Assemble input layout
        input_layout.addLayout(username_layout)
        input_layout.addLayout(apikey_layout)
        input_layout.addWidget(self.remember_me)
        input_layout.addLayout(tags_layout)
        input_layout.addLayout(limit_layout)
        input_layout.addLayout(dir_layout)
        
        layout.addLayout(input_layout)
        
        # Progress display
        self.progress_display = QTextEdit()
        self.progress_display.setReadOnly(True)
        self.progress_display.setMinimumHeight(150)
        layout.addWidget(self.progress_display)
        
        # Buttons layout
        button_layout = QHBoxLayout()
        self.download_button = QPushButton("Start Download")
        self.stop_button = QPushButton("Stop Download")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setEnabled(False)
        
        self.download_button.clicked.connect(self.start_download)
        self.stop_button.clicked.connect(self.stop_download)
        
        button_layout.addStretch()
        button_layout.addWidget(self.download_button)
        button_layout.addWidget(self.stop_button)
        
        layout.addLayout(button_layout)
        
        # Load previous settings if any
        self.load_settings()
        
        self.download_thread = None

    def load_settings(self):
        remember_me = self.settings.value('remember_me', False, type=bool)
        self.remember_me.setChecked(remember_me)
        
        if remember_me:
            self.username_input.setText(self.settings.value('username', ''))
            self.apikey_input.setText(self.settings.value('api_key', ''))
            self.tags_input.setText(self.settings.value('tags', ''))
            self.dir_input.setText(self.settings.value('save_directory', str(Path.home() / 'Downloads')))
            self.limit_input.setText(self.settings.value('limit', '320'))
        else:
            self.settings.remove('username')
            self.settings.remove('api_key')
            self.settings.remove('tags')
            self.settings.remove('save_directory')
            self.settings.remove('limit')
            
            self.dir_input.setText(str(Path.home() / 'Downloads'))
            self.limit_input.setText('320')

    def save_settings(self):
        remember_me = self.remember_me.isChecked()
        self.settings.setValue('remember_me', remember_me)
        
        if remember_me:
            self.settings.setValue('username', self.username_input.text())
            self.settings.setValue('api_key', self.apikey_input.text())
            self.settings.setValue('tags', self.tags_input.text())
            self.settings.setValue('save_directory', self.dir_input.text())
            self.settings.setValue('limit', self.limit_input.text())
        else:
            self.settings.remove('username')
            self.settings.remove('api_key')
            self.settings.remove('tags')
            self.settings.remove('save_directory')
            self.settings.remove('limit')

    def select_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if directory:
            self.dir_input.setText(directory)
            if self.remember_me.isChecked():
                self.save_settings()

    def create_settings_dict(self):
        return {
            "credentials": {
                "username": self.username_input.text(),
                "api_key": self.apikey_input.text()
            },
            "download": {
                "save_directory": self.dir_input.text(),
                "tags": self.tags_input.text(),
                "limit": int(self.limit_input.text() or '320')
            }
        }

    def validate_inputs(self):
        if not self.tags_input.text():
            QMessageBox.warning(self, "Validation Error", "Please enter tags to search")
            return False
        if not self.dir_input.text():
            QMessageBox.warning(self, "Validation Error", "Please select a save directory")
            return False
        
        try:
            limit = int(self.limit_input.text() or '320')
            if limit < 1:
                QMessageBox.warning(self, "Validation Error", "Download limit must be at least 1")
                return False
            if limit > 10000:
                QMessageBox.warning(self, "Validation Error", "Download limit cannot exceed 10000")
                return False
        except ValueError:
            QMessageBox.warning(self, "Validation Error", "Please enter a valid number for download limit")
            return False
            
        return True

    def start_download(self):
        if not self.validate_inputs():
            return
            
        if self.remember_me.isChecked():
            self.save_settings()
            
        settings_dict = self.create_settings_dict()
        
        self.download_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.progress_display.clear()
        
        self.download_thread = DownloaderThread(settings_dict)
        self.download_thread.progress_signal.connect(self.update_progress)
        self.download_thread.download_complete.connect(self.download_finished)
        self.download_thread.error_signal.connect(self.handle_error)
        self.download_thread.start()

    def stop_download(self):
        if self.download_thread and self.download_thread.isRunning():
            reply = QMessageBox.question(
                self,
                'Confirmation',
                'Are you sure you want to stop the download?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.download_thread.stop()
                self.progress_display.append("\nStopping download...")
                self.stop_button.setEnabled(False)

    def update_progress(self, message):
        self.progress_display.append(message)
        self.progress_display.verticalScrollBar().setValue(
            self.progress_display.verticalScrollBar().maximum()
        )

    def download_finished(self):
        self.download_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.progress_display.append("\nDownload process completed!")

    def handle_error(self, error_message):
        self.progress_display.append(f"\nError: {error_message}")
        self.download_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def closeEvent(self, event):
        if self.download_thread and self.download_thread.isRunning():
            reply = QMessageBox.question(
                self,
                'Confirmation',
                'A download is in progress. Are you sure you want to quit?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.download_thread.stop()
                self.download_thread.wait()
            else:
                event.ignore()
                return
        event.accept()

def main():
    app = QApplication(sys.argv)
    
    from PyQt6.QtGui import QFont
    font = QFont("Segoe UI", 9)
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

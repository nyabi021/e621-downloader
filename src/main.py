import sys
import os
import asyncio
import aiohttp
import ssl
import base64
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple, Set
from pathlib import Path

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                            QTextEdit, QFileDialog, QMessageBox,
                            QCheckBox, QProgressBar, QTabWidget,
                            QGridLayout, QSpinBox, QComboBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings, QSize
from PyQt6.QtGui import QFont, QIntValidator, QIcon

# --------------------------------
# Utility Classes
# --------------------------------

class SettingsManager:
    """Manages application settings and credentials"""
    def __init__(self):
        self.settings = QSettings('e621Downloader', 'Settings')
        
    def save_credentials(self, username: str, api_key: str, remember: bool):
        self.settings.setValue('remember_me', remember)
        
        if remember:
            self.settings.setValue('username', username)
            self.settings.setValue('api_key', api_key)
        else:
            self.settings.remove('username')
            self.settings.remove('api_key')
            
    def load_credentials(self) -> Tuple[str, str, bool]:
        remember = self.settings.value('remember_me', False, type=bool)
        username = ""
        api_key = ""
        
        if remember:
            username = self.settings.value('username', '')
            api_key = self.settings.value('api_key', '')
                    
        return username, api_key, remember
        
    def save_download_settings(self, tags: str, save_dir: str, limit: int):
        self.settings.setValue('tags', tags)
        self.settings.setValue('save_directory', save_dir)
        self.settings.setValue('limit', limit)
        
    def load_download_settings(self) -> Tuple[str, str, int]:
        tags = self.settings.value('tags', '')
        save_dir = self.settings.value('save_directory', str(Path.home() / 'Downloads'))
        limit = self.settings.value('limit', 320, type=int)
        
        return tags, save_dir, limit
        
    def save_theme_settings(self, use_system_theme: bool, theme: str):
        self.settings.setValue('use_system_theme', use_system_theme)
        self.settings.setValue('theme', theme)
        
    def load_theme_settings(self) -> Tuple[bool, str]:
        use_system_theme = self.settings.value('use_system_theme', True, type=bool)
        theme = self.settings.value('theme', 'light')
        
        return use_system_theme, theme


# --------------------------------
# API and Download Classes
# --------------------------------

@dataclass
class APIConfig:
    base_url: str
    delay: float
    user_agent: str


@dataclass
class Credentials:
    username: str
    api_key: str


@dataclass
class DownloadConfig:
    save_directory: str
    tags: str
    limit: int


@dataclass
class DownloadFile:
    url: str
    filename: str
    post_id: str
    artist: str


class ConfigValidator:
    @staticmethod
    def validate_config(config: Dict[str, Any]) -> bool:
        required_fields = {
            'api': ['base_url', 'delay', 'user_agent'],
            'credentials': ['username', 'api_key'],
            'download': ['tags', 'save_directory', 'limit']
        }
        
        try:
            for section, fields in required_fields.items():
                if section not in config:
                    raise ValueError(f"Missing section: {section}")
                for field in fields:
                    if field not in config[section]:
                        raise ValueError(f"Missing field: {field} in section {section}")
            return True
        except ValueError as e:
            return False


class APIClient:
    def __init__(self, api_config: APIConfig, credentials: Credentials):
        self.api_config = api_config
        self.credentials = credentials
        self.retry_count = 3
        self.retry_delay = 5
        self.base_url = self.api_config.base_url.rstrip('/')
        self._session = None
        
    async def initialize(self):
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        timeout = aiohttp.ClientTimeout(total=30)
        
        headers = {
            'User-Agent': self.api_config.user_agent,
            'Authorization': f'Basic {self._encode_credentials()}'
        }
        
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self._session = aiohttp.ClientSession(
            headers=headers,
            connector=connector,
            timeout=timeout
        )
            
    def _encode_credentials(self) -> str:
        credentials = f"{self.credentials.username}:{self.credentials.api_key}"
        return base64.b64encode(credentials.encode()).decode()
        
    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None
            
    async def _make_request(self, endpoint: str, params=None) -> Optional[Dict]:
        if not self._session:
            await self.initialize()
            
        url = f"{self.base_url}/{endpoint}"
        
        for attempt in range(self.retry_count):
            try:
                async with self._session.get(url, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 401:
                        return None
                    else:
                        pass
                        
            except aiohttp.ClientError as e:
                if attempt < self.retry_count - 1:
                    await asyncio.sleep(self.retry_delay)
                    
        return None
            
    async def verify_login(self) -> bool:
        """Verify if the API credentials are valid"""
        result = await self._make_request('posts.json', {'limit': 1})
        return result is not None
        
    async def get_posts(self, tags: str, limit: int = 100) -> List[Dict]:
        """Fetch posts that match the given tags"""
        result = await self._make_request('posts.json', {'tags': tags, 'limit': limit})
        
        if not result:
            return []
            
        return result.get('posts', [])


class FileDownloader:
    def __init__(self, save_directory: str, retry_count: int = 3, retry_delay: int = 5):
        self.save_directory = save_directory
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.session = None
            
    async def initialize(self):
        self.session = aiohttp.ClientSession()
        
    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None
            
    def _sanitize_filename(self, filename: str) -> str:
        # Remove invalid characters
        invalid_chars = '<>:"/\\|?*'
        sanitized = ''.join(c for c in filename if c not in invalid_chars)
        
        # Replace multiple spaces with a single space
        sanitized = ' '.join(sanitized.split())
        
        # Ensure filename isn't too long
        if len(sanitized) > 100:
            name_parts = sanitized.split('.')
            if len(name_parts) > 1:
                extension = name_parts[-1]
                base_name = '.'.join(name_parts[:-1])
                sanitized = f"{base_name[:95]}.{extension}"
            else:
                sanitized = f"{sanitized[:100]}"
                
        return sanitized
        
    async def download_file(self, download_file: DownloadFile) -> bool:
        if not self.session:
            await self.initialize()
            
        # Ensure save directory exists
        os.makedirs(self.save_directory, exist_ok=True)
        
        # Sanitize filename
        sanitized_filename = self._sanitize_filename(download_file.filename)
        filepath = Path(self.save_directory) / sanitized_filename
        
        # Check if file exists
        if filepath.exists():
            return True
            
        # Create a temp file for downloading
        temp_filepath = Path(f"{filepath}.part")
        downloaded_size = 0
        resume_download = False
        
        if temp_filepath.exists():
            downloaded_size = temp_filepath.stat().st_size
            resume_download = True
        
        for attempt in range(self.retry_count):
            try:
                headers = {}
                if resume_download and downloaded_size > 0:
                    headers['Range'] = f'bytes={downloaded_size}-'
                    
                async with self.session.get(download_file.url, headers=headers) as response:
                    if response.status == 200 or (resume_download and response.status == 206):
                        mode = 'ab' if resume_download else 'wb'
                        
                        with open(temp_filepath, mode) as f:
                            while True:
                                chunk = await response.content.read(8192)
                                if not chunk:
                                    break
                                f.write(chunk)
                                
                        # Download completed, rename file
                        temp_filepath.rename(filepath)
                        
                        return True
                    else:
                        pass
                        
            except aiohttp.ClientError as e:
                if attempt < self.retry_count - 1:
                    await asyncio.sleep(self.retry_delay)
                    
        return False


class DownloadTracker:
    def __init__(self):
        self.downloaded_files = 0
        self.total_files = 0
        self.failed_downloads = 0
        
    def add_files(self, count: int):
        self.total_files += count
        
    def register_download(self, success: bool):
        if success:
            self.downloaded_files += 1
        else:
            self.failed_downloads += 1
            
    def get_stats(self) -> Dict[str, int]:
        return {
            "downloaded": self.downloaded_files,
            "failed": self.failed_downloads,
            "total": self.total_files
        }
        
    def get_progress_percentage(self) -> int:
        if self.total_files == 0:
            return 0
        return int((self.downloaded_files + self.failed_downloads) / self.total_files * 100)


class DownloaderThread(QThread):
    progress_signal = pyqtSignal(str)
    progress_update = pyqtSignal(int, int, int)  # current, total, percentage
    download_complete = pyqtSignal()
    error_signal = pyqtSignal(str)
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.running = True
        self.downloader = None
        self.tracker = DownloadTracker()
        self.api_client = None
        
    def run(self):
        asyncio.run(self.download_process())
        
    async def download_process(self):
        try:
            # Setup API client
            self.api_client = APIClient(
                APIConfig(**self.config['api']),
                Credentials(**self.config['credentials'])
            )
            
            await self.api_client.initialize()
            
            # Setup file downloader
            self.downloader = FileDownloader(
                self.config['download']['save_directory']
            )
            
            await self.downloader.initialize()
            
            # Login verification
            self.progress_signal.emit(f"Attempting to login as {self.config['credentials']['username']}")
            if not await self.api_client.verify_login():
                self.error_signal.emit("Login failed! Check your credentials.")
                return
                
            self.progress_signal.emit("Login successful!")
            
            # Start download process
            tags = self.config['download']['tags']
            limit = self.config['download']['limit']
            
            self.progress_signal.emit(f"Fetching posts with tags: {tags}")
            
            # Get posts
            posts = await self.api_client.get_posts(tags, limit)
            
            if not posts:
                self.progress_signal.emit("No posts found with given tags.")
                self.download_complete.emit()
                return
                
            self.progress_signal.emit(f"Found {len(posts)} posts")
            
            # Prepare downloads
            download_files = []
            
            for post in posts:
                if not self.running:
                    break
                    
                url = post.get('file', {}).get('url')
                if not url:
                    continue
                    
                post_id = str(post.get('id', 'unknown'))
                artists = post.get('tags', {}).get('artist', ['unknown'])
                artist = artists[0] if artists else 'unknown'
                ext = url.split('.')[-1]
                
                filename = f"{artist}_{post_id}.{ext}"
                
                download_files.append(DownloadFile(
                    url=url,
                    filename=filename,
                    post_id=post_id,
                    artist=artist
                ))
                
            # Update tracker with total files
            self.tracker.add_files(len(download_files))
            self.progress_update.emit(
                self.tracker.downloaded_files,
                self.tracker.total_files,
                self.tracker.get_progress_percentage()
            )
            
            # Download files sequentially
            for i, download_file in enumerate(download_files):
                if not self.running:
                    self.progress_signal.emit("\nDownload interrupted by user.")
                    break
                    
                self.progress_signal.emit(f"Downloading {download_file.filename} ({i+1}/{len(download_files)})")
                
                success = await self.downloader.download_file(download_file)
                self.tracker.register_download(success)
                
                # Update progress
                if success:
                    self.progress_signal.emit(f"Successfully downloaded {download_file.filename}")
                else:
                    self.progress_signal.emit(f"Failed to download {download_file.filename}")
                
                self.progress_update.emit(
                    self.tracker.downloaded_files,
                    self.tracker.total_files,
                    self.tracker.get_progress_percentage()
                )
                
                # Respect API rate limits
                if i < len(download_files) - 1 and self.running:
                    await asyncio.sleep(self.api_client.api_config.delay)
            
            # Completion message
            stats = self.tracker.get_stats()
            self.progress_signal.emit(
                f"\nDownload completed! "
                f"Total: {stats['downloaded']} downloaded, "
                f"{stats['failed']} failed"
            )
            
            self.download_complete.emit()
            
        except Exception as e:
            error_message = f"Download error: {str(e)}"
            self.error_signal.emit(error_message)
        finally:
            # Cleanup
            if self.api_client:
                await self.api_client.close()
            if self.downloader:
                await self.downloader.close()
                
    def stop(self):
        self.running = False


# --------------------------------
# Theme Management
# --------------------------------

class ThemeManager:
    def __init__(self):
        self.settings_manager = SettingsManager()
        self.use_system_theme, self.theme = self.settings_manager.load_theme_settings()
        
    def get_system_theme(self):
        return "dark" if QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark else "light"
        
    def get_current_theme(self):
        if self.use_system_theme:
            return self.get_system_theme()
        return self.theme
        
    def set_theme(self, use_system_theme, theme=None):
        self.use_system_theme = use_system_theme
        if not use_system_theme and theme:
            self.theme = theme
        self.settings_manager.save_theme_settings(self.use_system_theme, self.theme)
        
    def get_stylesheet(self):
        current_theme = self.get_current_theme()
        
        if current_theme == "light":
            return """
                QMainWindow, QWidget {
                    background-color: #f5f5f5;
                }
                QLabel, QCheckBox {
                    font-size: 12px;
                    color: #333333;
                }
                QLineEdit, QSpinBox, QComboBox {
                    padding: 8px;
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    background-color: white;
                    font-size: 12px;
                }
                QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
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
                QPushButton#browseButton {
                    background-color: #6c757d;
                }
                QPushButton#browseButton:hover {
                    background-color: #5a6268;
                }
                QTextEdit {
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    background-color: white;
                    color: #212529;
                    font-family: "Consolas", monospace;
                    font-size: 12px;
                    padding: 8px;
                }
                QProgressBar {
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    background-color: white;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #007bff;
                }
                QTabWidget::pane {
                    border: 1px solid #cccccc;
                    background-color: white;
                }
                QTabBar::tab {
                    background-color: #e9ecef;
                    border: 1px solid #cccccc;
                    border-bottom: none;
                    padding: 8px 16px;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected {
                    background-color: white;
                }
            """
        else:  # Dark theme
            return """
                QMainWindow, QWidget {
                    background-color: #212529;
                }
                QLabel, QCheckBox {
                    font-size: 12px;
                    color: #f8f9fa;
                }
                QLineEdit, QSpinBox, QComboBox {
                    padding: 8px;
                    border: 1px solid #495057;
                    border-radius: 4px;
                    background-color: #343a40;
                    color: #f8f9fa;
                    font-size: 12px;
                }
                QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                    border: 1px solid #0d6efd;
                }
                QPushButton {
                    padding: 8px 16px;
                    border: none;
                    border-radius: 4px;
                    font-size: 12px;
                    color: white;
                    background-color: #0d6efd;
                }
                QPushButton:hover {
                    background-color: #0b5ed7;
                }
                QPushButton:pressed {
                    background-color: #0a58ca;
                }
                QPushButton:disabled {
                    background-color: #6c757d;
                }
                QPushButton#stopButton {
                    background-color: #6c757d;
                }
                QPushButton#stopButton:hover {
                    background-color: #5c636a;
                }
                QPushButton#browseButton {
                    background-color: #6c757d;
                }
                QPushButton#browseButton:hover {
                    background-color: #5c636a;
                }
                QTextEdit {
                    border: 1px solid #495057;
                    border-radius: 4px;
                    background-color: #343a40;
                    color: #f8f9fa;
                    font-family: "Consolas", monospace;
                    font-size: 12px;
                    padding: 8px;
                }
                QProgressBar {
                    border: 1px solid #495057;
                    border-radius: 4px;
                    background-color: #343a40;
                    color: #f8f9fa;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #0d6efd;
                }
                QTabWidget::pane {
                    border: 1px solid #495057;
                    background-color: #343a40;
                }
                QTabBar::tab {
                    background-color: #1e2125;
                    border: 1px solid #495057;
                    border-bottom: none;
                    padding: 8px 16px;
                    color: #f8f9fa;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected {
                    background-color: #343a40;
                }
            """


# --------------------------------
# UI Components
# --------------------------------

class LoginTab(QWidget):
    def __init__(self, settings_manager):
        super().__init__()
        self.settings_manager = settings_manager
        self.init_ui()
        self.load_settings()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # Username layout
        username_layout = QVBoxLayout()
        username_label = QLabel("Username")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter your e621 username")
        username_layout.addWidget(username_label)
        username_layout.addWidget(self.username_input)
        
        # API Key layout
        api_key_layout = QVBoxLayout()
        api_key_label = QLabel("API Key")
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Enter your API key")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_key_layout.addWidget(api_key_label)
        api_key_layout.addWidget(self.api_key_input)
        
        # Remember me checkbox
        self.remember_me = QCheckBox("Remember Me")
        
        # Add layouts to main layout
        layout.addLayout(username_layout)
        layout.addLayout(api_key_layout)
        layout.addWidget(self.remember_me)
        layout.addStretch()
        
    def load_settings(self):
        username, api_key, remember = self.settings_manager.load_credentials()
        self.username_input.setText(username)
        self.api_key_input.setText(api_key)
        self.remember_me.setChecked(remember)
        
    def get_credentials(self) -> Tuple[str, str, bool]:
        return (
            self.username_input.text(),
            self.api_key_input.text(),
            self.remember_me.isChecked()
        )
        
    def save_settings(self):
        username, api_key, remember = self.get_credentials()
        self.settings_manager.save_credentials(username, api_key, remember)


class DownloadTab(QWidget):
    def __init__(self, settings_manager):
        super().__init__()
        self.settings_manager = settings_manager
        self.init_ui()
        self.load_settings()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # Tags layout
        tags_layout = QVBoxLayout()
        tags_label = QLabel("Tags")
        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("Enter tags (space separated)")
        tags_layout.addWidget(tags_label)
        tags_layout.addWidget(self.tags_input)

        # Max downloads layout
        limit_layout = QVBoxLayout()
        limit_label = QLabel("Maximum Images (0 = no limit)")
        self.limit_input = QLineEdit()
        self.limit_input.setPlaceholderText("Enter maximum number of images (default: 320)")
        self.limit_input.setText("320")  
        self.limit_input.setValidator(QIntValidator(0, 10000))
        limit_layout.addWidget(limit_label)
        limit_layout.addWidget(self.limit_input)
        
        # Save directory layout
        dir_layout = QVBoxLayout()
        dir_label = QLabel("Save Directory")
        dir_input_layout = QHBoxLayout()
        self.dir_input = QLineEdit()
        self.dir_input.setPlaceholderText("Select save directory")
        self.dir_button = QPushButton("Browse")
        self.dir_button.setObjectName("browseButton")
        self.dir_button.clicked.connect(self.select_directory)
        dir_input_layout.addWidget(self.dir_input)
        dir_input_layout.addWidget(self.dir_button)
        dir_layout.addWidget(dir_label)
        dir_layout.addLayout(dir_input_layout)
        
        # Add layouts to main layout
        layout.addLayout(tags_layout)
        layout.addLayout(limit_layout)
        layout.addLayout(dir_layout)
        layout.addStretch()
        
    def load_settings(self):
        tags, save_dir, limit = self.settings_manager.load_download_settings()
        self.tags_input.setText(tags)
        self.dir_input.setText(save_dir)
        self.limit_input.setText(str(limit))
        
    def get_settings(self) -> Tuple[str, str, int]:
        return (
            self.tags_input.text(),
            self.dir_input.text(),
            int(self.limit_input.text() or 320)
        )
        
    def save_settings(self):
        tags, save_dir, limit = self.get_settings()
        self.settings_manager.save_download_settings(tags, save_dir, limit)
        
    def select_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if directory:
            self.dir_input.setText(directory)


class SettingsTab(QWidget):
    theme_changed = pyqtSignal()
    
    def __init__(self, theme_manager):
        super().__init__()
        self.theme_manager = theme_manager
        self.init_ui()
        self.load_settings()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Theme settings
        theme_group_layout = QVBoxLayout()
        theme_label = QLabel("Theme Settings")
        theme_label.setStyleSheet("font-weight: bold;")
        
        # System theme checkbox
        self.system_theme_check = QCheckBox("Use System Theme")
        self.system_theme_check.toggled.connect(self.toggle_system_theme)
        
        # Theme selection
        theme_selection_layout = QHBoxLayout()
        theme_selection_label = QLabel("Select Theme:")
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        self.theme_combo.currentTextChanged.connect(self.change_theme)
        theme_selection_layout.addWidget(theme_selection_label)
        theme_selection_layout.addWidget(self.theme_combo)
        
        # Add to group layout
        theme_group_layout.addWidget(theme_label)
        theme_group_layout.addWidget(self.system_theme_check)
        theme_group_layout.addLayout(theme_selection_layout)
        
        # Add to main layout
        layout.addLayout(theme_group_layout)
        layout.addStretch()
        
    def load_settings(self):
        use_system_theme, theme = self.theme_manager.use_system_theme, self.theme_manager.theme
        self.system_theme_check.setChecked(use_system_theme)
        self.theme_combo.setCurrentText("Light" if theme == "light" else "Dark")
        self.theme_combo.setEnabled(not use_system_theme)
        
    def toggle_system_theme(self, checked):
        self.theme_combo.setEnabled(not checked)
        self.theme_manager.set_theme(checked, self.theme_manager.theme)
        self.theme_changed.emit()
        
    def change_theme(self, theme_text):
        if not self.system_theme_check.isChecked():
            theme = "light" if theme_text == "Light" else "dark"
            self.theme_manager.set_theme(False, theme)
            self.theme_changed.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("e621 Downloader")
        self.setMinimumSize(700, 500)
        
        # Initialize managers
        self.settings_manager = SettingsManager()
        self.theme_manager = ThemeManager()
        
        self.init_ui()
        self.apply_theme()
        
        self.download_thread = None

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        
        # Create tabs
        self.login_tab = LoginTab(self.settings_manager)
        self.download_tab = DownloadTab(self.settings_manager)
        self.settings_tab = SettingsTab(self.theme_manager)
        
        # Connect signals
        self.settings_tab.theme_changed.connect(self.apply_theme)
        
        # Add tabs
        self.tab_widget.addTab(self.login_tab, "Login")
        self.tab_widget.addTab(self.download_tab, "Download Settings")
        self.tab_widget.addTab(self.settings_tab, "App Settings")
        
        main_layout.addWidget(self.tab_widget)
        
        # Progress display and controls
        progress_layout = QVBoxLayout()
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v/%m - %p%")
        progress_layout.addWidget(self.progress_bar)
        
        # Text log
        self.progress_display = QTextEdit()
        self.progress_display.setReadOnly(True)
        self.progress_display.setMinimumHeight(150)
        progress_layout.addWidget(self.progress_display)
        
        # Button layout
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
        
        progress_layout.addLayout(button_layout)
        main_layout.addLayout(progress_layout)

    def apply_theme(self):
        stylesheet = self.theme_manager.get_stylesheet()
        self.setStyleSheet(stylesheet)
        
        # Connect to system theme changes when available
        try:
            QApplication.instance().styleHints().colorSchemeChanged.connect(self.apply_theme)
        except AttributeError:
            # Older Qt versions might not have this signal
            pass

    def validate_inputs(self):
        # Get data from tabs
        username, api_key, _ = self.login_tab.get_credentials()
        tags, save_dir, _ = self.download_tab.get_settings()
        
        if not username:
            QMessageBox.warning(self, "Validation Error", "Please enter your username")
            self.tab_widget.setCurrentWidget(self.login_tab)
            return False
            
        if not api_key:
            QMessageBox.warning(self, "Validation Error", "Please enter your API key")
            self.tab_widget.setCurrentWidget(self.login_tab)
            return False
            
        if not tags:
            QMessageBox.warning(self, "Validation Error", "Please enter tags to search")
            self.tab_widget.setCurrentWidget(self.download_tab)
            return False
            
        if not save_dir:
            QMessageBox.warning(self, "Validation Error", "Please select a save directory")
            self.tab_widget.setCurrentWidget(self.download_tab)
            return False
            
        return True

    def create_config_dict(self):
        username, api_key, _ = self.login_tab.get_credentials()
        tags, save_dir, limit = self.download_tab.get_settings()
        
        return {
            "credentials": {
                "username": username,
                "api_key": api_key
            },
            "download": {
                "save_directory": save_dir,
                "tags": tags,
                "limit": limit
            },
            "api": {
                "base_url": "https://e621.net",
                "delay": 1.0,
                "user_agent": f"e621Downloader/1.1.0 (by {username})"
            }
        }

    def start_download(self):
        if not self.validate_inputs():
            return
            
        # Save settings
        self.login_tab.save_settings()
        self.download_tab.save_settings()
            
        config_dict = self.create_config_dict()
        
        # Update UI
        self.download_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.progress_display.clear()
        self.progress_bar.setValue(0)
        
        # Start download thread
        self.download_thread = DownloaderThread(config_dict)
        self.download_thread.progress_signal.connect(self.update_progress_text)
        self.download_thread.progress_update.connect(self.update_progress_bar)
        self.download_thread.download_complete.connect(self.download_finished)
        self.download_thread.error_signal.connect(self.handle_error)
        self.download_thread.start()

    def stop_download(self):
        if self.download_thread and self.download_thread.isRunning():
            reply = QMessageBox.question(self, 'Confirmation', 
                                       'Are you sure you want to stop the download?',
                                       QMessageBox.StandardButton.Yes | 
                                       QMessageBox.StandardButton.No)
            
            if reply == QMessageBox.StandardButton.Yes:
                self.download_thread.stop()
                self.progress_display.append("\nStopping download...")
                self.stop_button.setEnabled(False)

    def update_progress_text(self, message):
        self.progress_display.append(message)
        self.progress_display.verticalScrollBar().setValue(
            self.progress_display.verticalScrollBar().maximum()
        )

    def update_progress_bar(self, current, total, percentage):
        self.progress_bar.setMaximum(total if total > 0 else 1)
        self.progress_bar.setValue(current)
        
        # Update window title with progress
        if total > 0:
            self.setWindowTitle(f"e621 Downloader - {percentage}%")

    def download_finished(self):
        self.download_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.progress_display.append("\nDownload process completed!")
        
        # Reset window title
        self.setWindowTitle("e621 Downloader")
        
        # Show download stats if available
        if self.download_thread and hasattr(self.download_thread, 'tracker'):
            stats = self.download_thread.tracker.get_stats()
            summary = (
                f"\nDownload Summary:\n"
                f"- Total files processed: {stats['total']}\n"
                f"- Successfully downloaded: {stats['downloaded']}\n"
                f"- Failed: {stats['failed']}"
            )
            self.progress_display.append(summary)

    def handle_error(self, error_message):
        self.progress_display.append(f"\nError: {error_message}")
        self.download_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def closeEvent(self, event):
        if self.download_thread and self.download_thread.isRunning():
            reply = QMessageBox.question(self, 'Confirmation', 
                                    'A download is in progress. Are you sure you want to quit?',
                                    QMessageBox.StandardButton.Yes | 
                                    QMessageBox.StandardButton.No)
            
            if reply == QMessageBox.StandardButton.Yes:
                self.download_thread.stop()
                self.download_thread.wait()
            else:
                event.ignore()
                return
        event.accept()


def main():
    app = QApplication(sys.argv)
    
    font = QFont("Segoe UI", 9)
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

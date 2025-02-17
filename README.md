# PawLoad

A desktop application built with PyQt6 that allows users to download images from e621.net using their API.

## Features

- User-friendly GUI interface
- Secure API key authentication
- Custom tag-based search
- Configurable download limits
- Save directory selection
- Progress tracking
- Remember me functionality
- Graceful error handling
- Download interruption support

## Requirements

- Python 3.6+
- PyQt6
- aiohttp
- asyncio

## Installation

1. Clone this repository:
```bash
git clone https://github.com/nyabi021/PawLoad.git
cd e621-downloader
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

## Usage

1. Run the application:
```bash
python main.py
```

2. Enter your e621.net credentials:
   - Username
   - API Key (Can be found in your e621.net account settings)

3. Configure download settings:
   - Enter tags to search for
   - Set maximum number of images to download (default: 320)
   - Select save directory
   - Optional: Check "Remember Me" to save your settings

4. Click "Start Download" to begin downloading

## Building from Source

To create a standalone executable:

1. Install PyInstaller:
```bash
pip install pyinstaller
```

2. Build the executable:
```bash
pyinstaller --name="PawLoad" --icon=icon.ico --windowed --onefile main.py
```

The executable will be created in the `dist` directory.

## Configuration

The application saves settings in the following locations:
- Windows: `%APPDATA%\E621Downloader\Settings`
- Linux: `~/.config/E621Downloader/Settings`
- macOS: `~/Library/Preferences/E621Downloader/Settings`

## Features in Detail

### Authentication
- Secure login using username and API key
- Option to save credentials locally

### Download Management
- Concurrent downloads using asyncio
- Progress tracking for each download
- Ability to stop downloads in progress
- Automatic skipping of existing files

### Search Options
- Support for complex tag combinations
- Configurable download limits
- Custom save directory selection

## Security

- Credentials are stored securely using the system's keychain
- SSL verification for all API requests
- No plaintext password storage

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is released under the MIT License. See the `LICENSE` file for details.

## Disclaimer

This software is not affiliated with e621.net. Please be respectful of the site's API rate limits and terms of service.

## Support

For support, please open an issue in the GitHub repository.
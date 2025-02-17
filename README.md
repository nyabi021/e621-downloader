# e621-downloader

A desktop application built with PyQt6 that allows you to download images from e621.net using tags.

## Features

- User-friendly GUI interface
- Tag-based search and download  
- Customizable download limits
- Save and remember user preferences
- Progress tracking for downloads
- SSL supported secure connections
- Rate limit handling
- Automatic file naming with artist attribution

## Requirements

- Python 3.8+
- PyQt6
- aiohttp
- ssl
- base64

## Installation

1. Clone the repository:
```bash
git clone https://github.com/nyabi021/e621-downloader.git
cd e621-downloader
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

## Usage

1. Run the application:
```bash
python src/main.py
```

2. Enter your e621.net credentials (username and API key)
3. Input your desired tags for searching
4. Set the maximum number of images to download
5. Choose a save directory
6. Click "Start Download" to begin

## Configuration

- **Remember Me**: Option to save your credentials and preferences locally
- **Maximum Images**: Customize how many images to download (1-10000)
- **Save Directory**: Choose where to save downloaded images
- **Tags**: Space-separated tags for searching images

## Build

To create an executable:
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --icon=assets/icon.ico src/main.py
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This tool is intended for educational purposes only. Users are responsible for complying with e621.net's terms of service and API usage guidelines.
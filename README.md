# jkdownloader

Batch downloader for complete anime series from [jkanime.net](https://jkanime.net/).
Give it a series URL and it collects the download links (Mediafire by default, Mega as
fallback) for every episode — or every season — ready to paste into
[JDownloader 2](https://jdownloader.org/jdownloader2).

No more opening episodes one by one and copy-pasting links by hand.

## Installation

With [uv](https://docs.astral.sh/uv/) (recommended, uses the lockfile):

```bash
uv sync
uv run jkanime_dl.py <URL>
```

Or plain pip:

```bash
pip install requests
python jkanime_dl.py <URL>
```

## Usage

```bash
# Whole series, Mediafire links
uv run jkanime_dl.py https://jkanime.net/tensei-shitara-slime-datta-ken/

# All seasons/OVAs of the franchise + CSV report
uv run jkanime_dl.py https://jkanime.net/tensei-shitara-slime-datta-ken/ --seasons --detail

# One JDownloader package per season, ready to import
uv run jkanime_dl.py https://jkanime.net/tensei-shitara-slime-datta-ken/ --seasons --crawljobs

# For more control and options use
uv run jkanime_dl.py --help
```

## Output files

| File                           | Contents                                                     |
| ------------------------------ | ------------------------------------------------------------ |
| `mediafire_<series>.txt`       | One working download link per line, ready to paste           |
| `<...>details.csv`             | Full report: season, episode, server, language, size, status |
| `<...>_jdcrawljobs/*.crawljob` | JDownloader job files, one per season                        |

## Importing into JDownloader 2

- **Plain links**: open the `.txt`, select all, copy and paste into the LinkGrabber tab (Not recommended because will be unordered).
- **`.crawljob` files (recommended)**: copy them into the `folderwatch` folder inside
  your JDownloader 2 installation directory (or just drag them onto the LinkGrabber
  window, or add it as a link container). They are imported automatically as one package per season, with the correct
  download folder already set.

## Disclaimer

Intended for personal use only.

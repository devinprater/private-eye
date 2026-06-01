# Private Eye

Private Eye describes live screen content for blind users with an Ollama vision
model. This repository contains two packages:

- An NVDA add-on for Windows.
- A Commentary/Jieshuo screen reader plugin for Android.

## Downloads

Download the latest packages from the
[GitHub releases page](https://github.com/devinprater/private-eye/releases).

- Install the `.nvda-addon` file with NVDA on Windows.
- Import the `.ppk` file with Commentary/Jieshuo on Android.

## Requirements

Private Eye expects an Ollama-compatible API. The default endpoint is
`http://127.0.0.1:11434`.

The NVDA add-on requires NVDA 2026.1 or later.

## Development

Run the Python tests with:

```powershell
python -m pytest
```

Build the NVDA add-on with:

```powershell
scons
```

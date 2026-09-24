# Data Validation Hub

Integrated desktop validation platform for source-to-o9 reconciliation.

## Validators

- Actuals Validation
- UOM Conversion Validation
- o9 Compare Past ASP
- ASP Override Current & Future

## Run from source

Python 3.12 is recommended.

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
python main.py
```

## Build the Windows application

The project uses PyInstaller and produces a Windows one-folder application.

On Windows, run:

```text
build\\build_windows.bat
```

The result is:

```text
dist\\DataValidationHub\\DataValidationHub.exe
```

Copy the complete `DataValidationHub` folder to another Windows laptop and run the EXE. Python does not need to be installed on the target laptop.

### GitHub Actions build

The repository includes `.github/workflows/build-windows.yml`. Run the workflow manually from GitHub Actions to build a Windows ZIP artifact using `windows-latest`.

Tagging a release such as `v1.0.0` also creates a GitHub release asset.

## Application data

When packaged, reports and logs are written to a per-user writable directory:

```text
%LOCALAPPDATA%\\DataValidationHub\\outputs
%LOCALAPPDATA%\\DataValidationHub\\logs
```

This avoids write-permission problems when the application is installed under `Program Files`.

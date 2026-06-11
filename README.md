# AOS

This repository contains AOS-related training and operations modules.

## Modules

- [SBE Governance Training Module](training/sbe-governance-module/README.md)

## Replit

The repo is configured so Replit's **Run** button starts the SBE Governance
Training Module from its separate folder.

Manual shell command:

```bash
cd training/sbe-governance-module
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

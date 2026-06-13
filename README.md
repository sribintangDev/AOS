# AOS

This repository contains AOS-related training and operations modules.

## Modules

- [SBE Governance Training Module](training/sbe-governance-module/README.md)

## Replit

The repo is configured as a standalone Replit app for the SBE Governance
Training Module.

Manual shell command:

```bash
cd training/sbe-governance-module
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-5000}
```

Required production secret:

```text
AOS_TRAINING_DATABASE_URL=postgresql://postgres.hjwifekfwmdklaxbazpz:YOUR_PASSWORD@aws-1-ap-northeast-1.pooler.supabase.com:6543/postgres?sslmode=require
```

# Backend Setup

## Start the API with Uvicorn

Use this command to run the FastAPI app on port `8000`:

```powershell
python -m uvicorn src.api:app --reload --host 127.0.0.1 --port 8000
```

## Notes

- `src.api:app` means: load the `app` object from `Backend/src/api.py`.
- `--reload` restarts the server when backend files change.
- Change `--port 8000` to another port if `8000` is already in use.


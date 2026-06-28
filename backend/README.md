# Genesis Backend

Start the local API server from the backend directory:

```powershell
python run_server.py
```

The frontend development server proxies `/api` to `http://127.0.0.1:8000` by default.
Verify the backend with:

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing
```

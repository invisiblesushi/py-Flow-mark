"""Pixeldrain cloud upload provider."""

from __future__ import annotations

import base64
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .exceptions import CloudUploadError

PIXELDRAIN_API = "https://pixeldrain.com/api"
PIXELDRAIN_LIST_URL = "https://pixeldrain.com/l/{id}"
DEFAULT_UPLOAD_WORKERS = 10


# #region agent log
def _agent_dbg(hypothesis_id, location, message, data=None):
    import time
    try:
        with open(
            r"C:\Users\danie\Documents\GitHub\py-Flow-mark\debug-cc9b70.log",
            "a",
            encoding="utf-8",
        ) as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "cc9b70",
                        "hypothesisId": hypothesis_id,
                        "location": location,
                        "message": message,
                        "data": data or {},
                        "timestamp": int(time.time() * 1000),
                        "runId": "post-fix",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass
# #endregion


def _basic_auth_header(api_key: str) -> str:
    token = base64.b64encode(f":{api_key}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _request_json(method, url, *, api_key, data=None, content_type=None, timeout=120):
    headers = {
        "Authorization": _basic_auth_header(api_key),
        "User-Agent": "FlowMark/1.0",
        "Accept": "application/json",
    }
    body = data
    if content_type:
        headers["Content-Type"] = content_type
    if isinstance(data, (dict, list)):
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
            payload = json.loads(err_body) if err_body else {}
        except Exception:
            payload = {}
        message = payload.get("message") or e.reason or str(e)
        raise CloudUploadError(f"HTTP {e.code}: {message}") from e
    except urllib.error.URLError as e:
        raise CloudUploadError(f"Network error: {e.reason}") from e

    if not payload.get("success", True):
        raise CloudUploadError(payload.get("message") or "Request failed")
    return payload


def upload_file(path, api_key, *, name=None):
    """
    Upload one file to Pixeldrain via PUT /file/{name}.
    Returns the file id string.
    """
    path = Path(path)
    if not path.is_file():
        raise CloudUploadError(f"File not found: {path}")

    api_key = (api_key or "").strip()
    if not api_key:
        raise CloudUploadError("Pixeldrain API key is required")

    filename = name or path.name
    encoded = urllib.parse.quote(filename, safe="")
    url = f"{PIXELDRAIN_API}/file/{encoded}"

    data = path.read_bytes()
    payload = _request_json(
        "PUT",
        url,
        api_key=api_key,
        data=data,
        content_type="application/octet-stream",
        timeout=300,
    )
    file_id = payload.get("id")
    if not file_id:
        raise CloudUploadError(f"Upload succeeded but no id returned for {path.name}")
    return str(file_id)


def create_album(api_key, title, file_ids):
    """
    Create a Pixeldrain list (album) from uploaded file ids.
    Returns (album_id, album_url).
    """
    api_key = (api_key or "").strip()
    if not api_key:
        raise CloudUploadError("Pixeldrain API key is required")
    if not file_ids:
        raise CloudUploadError("No files to add to the album")

    title = (title or "").strip() or "FlowMark Album"
    body = {
        "title": title,
        "anonymous": False,
        "files": [{"id": fid} for fid in file_ids],
    }
    payload = _request_json(
        "POST",
        f"{PIXELDRAIN_API}/list",
        api_key=api_key,
        data=body,
        timeout=60,
    )
    album_id = payload.get("id")
    if not album_id:
        raise CloudUploadError("Album created but no id returned")
    album_id = str(album_id)
    return album_id, PIXELDRAIN_LIST_URL.format(id=album_id)


def _clamp_workers(value, fallback=DEFAULT_UPLOAD_WORKERS):
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = fallback
    return max(1, min(32, n))


def upload_folder(files, api_key, album_name, progress_callback=None,
                  max_workers=DEFAULT_UPLOAD_WORKERS):
    """
    Upload files concurrently and create an album.

    files: iterable of Path / str
    max_workers: parallel upload threads (clamped 1–32)
    Returns dict: {album_id, album_url, file_ids, uploaded, failed}
    """
    api_key = (api_key or "").strip()
    if not api_key:
        raise CloudUploadError("Pixeldrain API key is required for cloud upload")

    paths = [Path(p) for p in files]
    paths = [p for p in paths if p.is_file()]
    if not paths:
        raise CloudUploadError("No output files to upload")

    workers = _clamp_workers(max_workers)
    log_lock = threading.Lock()
    done_count = 0
    done_lock = threading.Lock()

    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    total = len(paths)
    log(
        f"☁️ Uploading {total} file{'s' if total != 1 else ''} to Pixeldrain "
        f"({workers} thread{'s' if workers != 1 else ''})…"
    )

    # #region agent log
    _agent_dbg(
        "A",
        "cloud/pixeldrain.py:upload_folder",
        "upload input path order",
        {"count": total, "first15": [p.name for p in paths[:15]]},
    )
    # #endregion

    # Preserve input order for the album
    results = [None] * total  # (ok, file_id_or_None, error_or_None)
    failed = []

    def _upload_one(index, path):
        nonlocal done_count
        try:
            file_id = upload_file(path, api_key)
            results[index] = (True, file_id, None)
            with done_lock:
                done_count += 1
                n = done_count
            with log_lock:
                log(f"☁️ [{n}/{total}] Uploaded {path.name} → {file_id}")
            return True, file_id, None
        except Exception as e:
            results[index] = (False, None, str(e))
            with done_lock:
                done_count += 1
                n = done_count
            with log_lock:
                log(f"☁️ [{n}/{total}] ❌ {path.name}: {e}")
            return False, None, str(e)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_upload_one, i, path): i
            for i, path in enumerate(paths)
        }
        for future in as_completed(futures):
            future.result()  # surface unexpected errors already handled inside

    file_ids = []
    album_names = []
    for i, path in enumerate(paths):
        ok, file_id, err = results[i] or (False, None, "unknown error")
        if ok and file_id:
            file_ids.append(file_id)
            album_names.append(path.name)
        else:
            failed.append((path.name, err or "upload failed"))

    # #region agent log
    _agent_dbg(
        "B",
        "cloud/pixeldrain.py:upload_folder",
        "album file order sent to Pixeldrain",
        {
            "count": len(album_names),
            "first15_names": album_names[:15],
            "first15_ids": file_ids[:15],
            "names_sorted_match": album_names[:15]
            == sorted(album_names, key=lambda n: n.lower())[:15],
        },
    )
    # #endregion

    if not file_ids:
        raise CloudUploadError("All uploads failed; album not created")

    album_id, album_url = create_album(api_key, album_name, file_ids)
    log(f"☁️ Album created: {album_url}")
    if failed:
        log(f"☁️ Warning: {len(failed)} file(s) failed to upload")

    return {
        "album_id": album_id,
        "album_url": album_url,
        "file_ids": file_ids,
        "uploaded": len(file_ids),
        "failed": failed,
    }


# Backwards-compatible aliases used by the public package API
upload_file_pixeldrain = upload_file
create_album_pixeldrain = create_album
upload_folder_to_pixeldrain = upload_folder

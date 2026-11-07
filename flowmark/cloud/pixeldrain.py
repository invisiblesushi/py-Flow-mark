"""Pixeldrain cloud upload provider."""

from __future__ import annotations

import base64
import json
import re
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
MIN_ALBUM_ID_LEN = 6
_ALBUM_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?pixeldrain\.com/(?:api/list|l)/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)
_ALBUM_ID_RE = re.compile(r"[A-Za-z0-9_-]+")


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
        "User-Agent": "FlowMark/1.0",
        "Accept": "application/json",
    }
    api_key = (api_key or "").strip()
    if api_key:
        headers["Authorization"] = _basic_auth_header(api_key)
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


def parse_album_id(value):
    """
    Return a Pixeldrain list id from a raw id or an album URL.

    Accepts ``https://pixeldrain.com/l/{id}`` and
    ``https://pixeldrain.com/api/list/{id}``.
    """
    raw = (value or "").strip()
    if not raw:
        raise CloudUploadError("Album ID is required")

    match = _ALBUM_URL_RE.search(raw)
    if match:
        return match.group(1)

    if "://" in raw or "pixeldrain.com" in raw.lower():
        raise CloudUploadError("Album ID is not valid")

    token = raw.split("?", 1)[0].split("#", 1)[0].strip().strip("/")
    if "/" in token:
        token = token.rsplit("/", 1)[-1]
    if not _ALBUM_ID_RE.fullmatch(token):
        raise CloudUploadError("Album ID is not valid")
    return token


def get_album(api_key, album_ref):
    """
    Fetch a Pixeldrain list. The API key is sent when present.
    Public lists can be read without one.
    Returns the list payload.
    """
    album_id = parse_album_id(album_ref)
    url = f"{PIXELDRAIN_API}/list/{urllib.parse.quote(album_id, safe='')}"
    payload = _request_json(
        "GET",
        url,
        api_key=(api_key or "").strip(),
        timeout=30,
    )
    if not isinstance(payload, dict) or not payload.get("id"):
        raise CloudUploadError("Album lookup returned an unexpected response")
    return payload


def _require_editable(payload):
    if payload.get("can_edit") is False:
        raise CloudUploadError(
            "This album cannot be edited with the current API key"
        )


def append_to_album(api_key, album_ref, file_ids):
    """
    Add file ids to an existing list.

    PUT /list/{id} replaces the file list, so the current files are read
    first and sent back ahead of the new ids. The existing title is kept.
    Returns (album_id, album_url).
    """
    api_key = (api_key or "").strip()
    if not api_key:
        raise CloudUploadError("Pixeldrain API key is required")
    if not file_ids:
        raise CloudUploadError("No files to add to the album")

    album_id = parse_album_id(album_ref)
    existing = get_album(api_key, album_id)
    _require_editable(existing)
    album_id = str(existing.get("id") or album_id)

    merged = []
    seen = set()
    for item in existing.get("files") or []:
        if not isinstance(item, dict):
            continue
        fid = item.get("id")
        if not fid:
            continue
        fid = str(fid)
        if fid in seen:
            continue
        seen.add(fid)
        entry = {"id": fid}
        if item.get("description") is not None:
            entry["description"] = item.get("description")
        merged.append(entry)

    for fid in file_ids:
        fid = str(fid)
        if fid in seen:
            continue
        seen.add(fid)
        merged.append({"id": fid})

    if not merged:
        raise CloudUploadError("No files to add to the album")

    body = {"files": merged}
    title = (existing.get("title") or "").strip()
    if title:
        body["title"] = title

    _request_json(
        "PUT",
        f"{PIXELDRAIN_API}/list/{urllib.parse.quote(album_id, safe='')}",
        api_key=api_key,
        data=body,
        timeout=60,
    )
    return album_id, PIXELDRAIN_LIST_URL.format(id=album_id)


def _clamp_workers(value, fallback=DEFAULT_UPLOAD_WORKERS):
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = fallback
    return max(1, min(32, n))


def upload_folder(files, api_key, album_name, progress_callback=None,
                  max_workers=DEFAULT_UPLOAD_WORKERS, album_id=None):
    """
    Upload files concurrently and create an album, or append to one.

    files: iterable of Path / str
    album_id: existing Pixeldrain list id or album URL. Empty creates a new list.
    max_workers: parallel upload threads (clamped 1–32)
    Returns dict: {album_id, album_url, file_ids, uploaded, failed}
    """
    api_key = (api_key or "").strip()
    if not api_key:
        raise CloudUploadError("Pixeldrain API key is required for cloud upload")

    target_id = (album_id or "").strip()
    if target_id:
        target_id = parse_album_id(target_id)
        existing = get_album(api_key, target_id)
        _require_editable(existing)
        target_id = str(existing.get("id") or target_id)

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
        if target_id:
            raise CloudUploadError("All uploads failed; album not updated")
        raise CloudUploadError("All uploads failed; album not created")

    if target_id:
        album_id, album_url = append_to_album(api_key, target_id, file_ids)
        log(f"☁️ Added {len(file_ids)} file(s) to album: {album_url}")
    else:
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

"""Download the Kaggle 2024 NIFTY options dataset pieces we actually need.

For each 2024 trading day only the NEAREST-expiry option file is fetched
(the strategy trades the nearest expiry), plus the 12 monthly spot files
and expiry.csv. Roughly 250 option files, ~500 MB total.

Auth: set KAGGLE_API_TOKEN (a KGAT_... token). Run from anywhere:

    python scripts/download_kaggle_2024.py --dest work/kaggle2024

Dataset: senthilkumarvaithi/historical-nifty-options-2024-all-expiries
(Apache 2.0). stdlib only.
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from anode.data.historical import nearest_expiry_files  # noqa: E402

DATASET = "senthilkumarvaithi/historical-nifty-options-2024-all-expiries"
BASE = "https://www.kaggle.com/api/v1/datasets"


def _request(url: str, token: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def list_all_files(token: str):
    names, page_token = [], None
    while True:
        url = "{}/list/{}".format(BASE, DATASET)
        if page_token:
            url += "?pageToken=" + urllib.parse.quote(page_token)
        d = json.loads(_request(url, token, timeout=60))
        names += [f["nameNullable"] for f in d.get("datasetFiles", [])]
        page_token = d.get("nextPageTokenNullable")
        if not page_token:
            return names


def download(name: str, dest: Path, token: str, attempts: int = 3) -> None:
    url = "{}/download/{}/{}".format(BASE, DATASET, urllib.parse.quote(name, safe=""))
    dest.parent.mkdir(parents=True, exist_ok=True)
    for i in range(attempts):
        try:
            dest.write_bytes(_request(url, token))
            return
        except Exception as exc:
            if i == attempts - 1:
                raise
            print("  retry {} for {}: {}".format(i + 1, name, exc))
            time.sleep(5 * (i + 1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default="work/kaggle2024")
    args = ap.parse_args()

    token = os.environ.get("KAGGLE_API_TOKEN", "").strip().strip("'\"")
    # tolerate a pasted shell line: export KAGGLE_API_TOKEN=KGAT_...
    if "KAGGLE_API_TOKEN=" in token:
        token = token.split("KAGGLE_API_TOKEN=", 1)[1].strip().strip("'\"")
    if not token:
        print("ERROR: the KAGGLE_API_TOKEN secret is not set (or empty). "
              "Add it under Settings -> Secrets and variables -> Actions.",
              file=sys.stderr)
        return 1
    if not token.startswith("KGAT_"):
        print("WARNING: token does not look like a KGAT_ token; trying anyway")
    try:
        _request(BASE + "/view/" + DATASET, token, timeout=30)
    except Exception as exc:
        print("ERROR: Kaggle rejected the token ({}). Check that the secret "
              "value is ONLY the token itself, e.g. KGAT_xxxx, with no "
              "'export ...' prefix, spaces, or quotes.".format(exc),
              file=sys.stderr)
        return 1

    dest = Path(args.dest)
    print("listing dataset files ...")
    names = list_all_files(token)
    print("{} files in dataset".format(len(names)))

    picks = nearest_expiry_files(names)
    spot_files = [n for n in names if "/2024Nifty/" in n]
    print("{} trade days (nearest expiry only), {} spot files".format(
        len(picks), len(spot_files)))

    download("2024/expiry.csv", dest / "expiry.csv", token)
    for n in sorted(spot_files):
        out = dest / "spot" / n.rsplit("/", 1)[-1]
        if not out.exists():
            print("spot:", n)
            download(n, out, token)
    for i, day in enumerate(sorted(picks), 1):
        name, _expiry = picks[day]
        out = dest / "options" / name.rsplit("/", 1)[-1]
        if out.exists():
            continue
        print("[{}/{}] {}".format(i, len(picks), name))
        download(name, out, token)
    print("done ->", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())

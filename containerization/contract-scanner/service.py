import argparse
import json
import logging
import os
from pathlib import Path
import pickle
import signal
import subprocess
import sys
import tempfile
import threading

import pandas as pd
import redis
import requests
from sqlalchemy import text
from sqlalchemy.types import Text
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from data_processing.sde_utils import db_connection


STATIC_TABLES = {
    "invTypes": ["typeID", "groupID", "typeName", "volume", "packagedVolume", "published"],
    "invGroups": ["groupID", "categoryID", "groupName"],
    "industryActivityMaterials": ["typeID", "activityID", "materialTypeID", "quantity"],
    "industryActivityProducts": ["typeID", "activityID", "productTypeID", "quantity"],
}
STATIC_FILES = (
    "types_packaged_volumes.json", "types.en-us.json", "groupIDs.yaml", "rig_type_ids.pkl",
)


def write_static_files(types, groups, destination):
    destination.mkdir(parents=True, exist_ok=True)
    volumes = types["packagedVolume"].fillna(types["volume"])
    if volumes.isna().any() or (volumes < 0).any():
        raise ValueError("Static data contains missing or negative item volumes")
    group_data = {
        int(row.groupID): {
            "categoryID": int(row.categoryID), "name": {"en": row.groupName},
        }
        for row in groups.itertuples()
    }
    type_data = {
        int(row.typeID): {"group_id": int(row.groupID), "name": row.typeName}
        for row in types.itertuples()
    }
    rig_groups = groups.loc[
        (groups["categoryID"] == 7) & groups["groupName"].str.contains("Rig ", na=False),
        "groupID",
    ]
    rigs = types.loc[types["groupID"].isin(rig_groups), "typeID"].astype(int).tolist()
    files = {
        "types_packaged_volumes.json": json.dumps({
            "packaged_volume": dict(zip(types["typeID"].astype(str), volumes)),
        }).encode("utf-8"),
        "types.en-us.json": json.dumps(type_data).encode("utf-8"),
        "groupIDs.yaml": yaml.safe_dump(group_data).encode("utf-8"),
        "rig_type_ids.pkl": pickle.dumps(rigs),
    }
    for name, content in files.items():
        temporary = destination / (name + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(destination / name)


def setup(refresh=False):
    for directory in ("static", "cache", "logs"):
        (ROOT / directory).mkdir(exist_ok=True)
    engine = db_connection()
    static_engine = db_connection(fuzz=True)
    cache = redis.Redis(host=os.environ["redis_host"], socket_timeout=10)
    cache.ping()
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with engine.begin() as connection:
        for statement in schema.split(";"):
            if statement.strip():
                connection.execute(text(statement))
        ready = connection.execute(text(
            "SELECT name FROM scanner_bootstrap WHERE name = 'static-v1'"
        )).first()
        if ready and not refresh:
            if all((ROOT / "static" / name).is_file() for name in STATIC_FILES):
                logging.info("Databases and static data already initialized")
                return
        connection.execute(text("DELETE FROM scanner_bootstrap WHERE name = 'static-v1'"))

    with tempfile.TemporaryDirectory(prefix="eve-static-") as directory:
        for table, columns in STATIC_TABLES.items():
            url = f"https://www.fuzzwork.co.uk/dump/latest/csv/{table}.csv"
            logging.info("Downloading static data: %s", table)
            path = Path(directory) / (table + ".csv")
            with requests.get(url, stream=True, timeout=(15, 300)) as response:
                response.raise_for_status()
                with path.open("wb") as target:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        target.write(chunk)
            count = 0
            for frame in pd.read_csv(path, usecols=columns, chunksize=5000):
                frame.to_sql(
                    table, con=static_engine, if_exists="replace" if count == 0 else "append",
                    index=False, chunksize=1000,
                    dtype={column: Text() for column in columns if column.endswith("Name")},
                )
                count += len(frame)
            if count == 0:
                raise RuntimeError(f"Static data table {table} is empty")
            logging.info("Imported %s: %s rows", table, count)

    types = pd.read_sql_query("SELECT * FROM invTypes", static_engine)
    groups = pd.read_sql_query("SELECT * FROM invGroups", static_engine)
    write_static_files(types, groups, ROOT / "static")
    cache.delete("blueprint_values_updated")
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO scanner_bootstrap (name, completed_at) VALUES ('static-v1', UTC_TIMESTAMP())"
        ))
    logging.info("Setup complete; scanner and browser can now start")


def run_scanner(once=False):
    interval = int(os.getenv("SCAN_INTERVAL_SECONDS", "600"))
    if interval < 1:
        raise ValueError("SCAN_INTERVAL_SECONDS must be a positive integer")
    stopping = threading.Event()
    process = None

    def stop(signum, frame):
        stopping.set()
        if process is not None and process.poll() is None:
            process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopping.is_set():
        logging.info("Starting contract scan")
        process = subprocess.Popen([sys.executable, "contracts_data.py"], cwd=ROOT)
        if stopping.is_set() and process.poll() is None:
            process.terminate()
        returncode = process.wait()
        if stopping.is_set():
            return
        if returncode:
            raise RuntimeError(f"Contract scan failed with exit code {returncode}")
        logging.info("Scan complete")
        if once:
            return
        logging.info("Next scan in %s seconds", interval)
        stopping.wait(interval)


def network_check():
    import socket
    import time
    for host in ("esi.evetech.net", "discord.com"):
        for family, name in ((socket.AF_UNSPEC, "IPv4+IPv6"), (socket.AF_INET, "IPv4 only")):
            started = time.monotonic()
            try:
                count = len(socket.getaddrinfo(host, 443, family, socket.SOCK_STREAM))
                logging.info("%s DNS (%s): %.2fs, %s addresses", host, name, time.monotonic() - started, count)
            except OSError as error:
                logging.error("%s DNS (%s) failed after %.2fs: %s", host, name, time.monotonic() - started, error)
        started = time.monotonic()
        try:
            socket.create_connection((host, 443), timeout=15).close()
            logging.info("%s TCP connect: %.2fs", host, time.monotonic() - started)
        except OSError as error:
            logging.error("%s TCP connect failed after %.2fs: %s", host, time.monotonic() - started, error)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Initialize and run the EVE contract scanner")
    parser.add_argument("command", choices=["setup", "run", "scan-once", "network-check"])
    parser.add_argument("--refresh-static", action="store_true")
    args = parser.parse_args()
    if args.command == "setup":
        setup(refresh=args.refresh_static)
    elif args.command == "network-check":
        network_check()
    else:
        run_scanner(once=args.command == "scan-once")

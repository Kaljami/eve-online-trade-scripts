import importlib.util
import json
import os
from pathlib import Path
import pickle
import re
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

import contract_browser
import contracts_data
from data_retrieval import order_data

spec = importlib.util.spec_from_file_location("scanner_service", Path(__file__).with_name("service.py"))
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


class PublicMarketTests(unittest.TestCase):
    @patch.dict(os.environ, {"CONTRACT_SCANNER_PUBLIC_MARKETS": "true"})
    def test_jita_filters_station_but_plex_keeps_all_locations(self):
        orders = [{"location_id": 60003760}, {"location_id": 42}]
        with patch.object(order_data, "get_num_pages", return_value=1) as pages, patch.object(
            order_data, "async_get_all_orders", new=AsyncMock(return_value=[orders]),
        ):
            self.assertEqual(order_data.get_all_orders_concurrent("Jita", "buy", None), orders[:1])
            pages.assert_called_with(10000002, "buy", None)
            self.assertEqual(order_data.get_all_orders_concurrent("Plex", "sell", None), orders)
            pages.assert_called_with(19000001, "sell", None)

    def test_disk_cache_uses_the_same_filename_for_read_and_write(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = os.getcwd()
            try:
                os.chdir(directory)
                cache = MagicMock()
                cache.get.return_value = None
                with patch.object(order_data, "redis_connection", return_value=cache):
                    orders = [{"type_id": 34, "price": 5}]
                    order_data.save_orders_to_cache("Jita", orders, "buy")
                    self.assertEqual(order_data.get_orders_from_cache("Jita", "buy"), orders)
            finally:
                os.chdir(previous)

    def test_failed_public_price_refresh_does_not_mark_it_as_complete(self):
        with patch.object(order_data, "get_all_orders_concurrent", return_value=[]), patch.object(
            order_data, "update_metadata",
        ) as metadata:
            with self.assertRaisesRegex(RuntimeError, "No public buy orders"):
                order_data.update_scanner_caches(force=True)
            metadata.assert_not_called()


class BootstrapTests(unittest.TestCase):
    def test_generates_legacy_files_with_packaged_volume_and_category_data(self):
        types = pd.DataFrame({
            "typeID": [1, 2, 3], "groupID": [10, 20, 30],
            "typeName": ["Ship", "Ship Blueprint", "Rig"],
            "volume": [1000, .01, 5], "packagedVolume": [100, None, None],
        })
        groups = pd.DataFrame({
            "groupID": [10, 20, 30], "categoryID": [6, 9, 7],
            "groupName": ["Frigate", "Blueprint", "Rig Armor"],
        })
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            service.write_static_files(types, groups, destination)
            volumes = json.loads((destination / "types_packaged_volumes.json").read_text())
            self.assertEqual(volumes["packaged_volume"], {"1": 100, "2": .01, "3": 5})
            type_data = json.loads((destination / "types.en-us.json").read_text())
            self.assertEqual(type_data["2"]["group_id"], 20)
            self.assertEqual(pickle.loads((destination / "rig_type_ids.pkl").read_bytes()), [3])

    def test_rejects_missing_volumes_instead_of_dropping_contract_items(self):
        types = pd.DataFrame({"volume": [None], "packagedVolume": [None]})
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "missing or negative"):
                service.write_static_files(types, pd.DataFrame(), Path(directory))

    @patch.object(service.signal, "signal")
    def test_scan_once_exposes_child_failure(self, signals):
        with patch.object(service.subprocess, "Popen") as process:
            process.return_value.wait.return_value = 1
            with self.assertRaisesRegex(RuntimeError, "exit code 1"):
                service.run_scanner(once=True)

class ScannerPersistenceTests(unittest.TestCase):
    def test_contracts_and_items_roll_back_together_on_failed_item_insert(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE contracts (contract_id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE contract_items (contract_id INTEGER)"))
        with patch.object(contracts_data.time, "sleep"):
            with self.assertRaises(OperationalError):
                contracts_data.save_dataframe_to_db(
                    pd.DataFrame({"contract_id": [123]}), "contracts", engine, "Genesis",
                    items_df=pd.DataFrame({"contract_id": [123], "unexpected_column": [1]}),
                )
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM contracts")).scalar(), 0)
        engine.dispose()

    def test_ignore_list_allows_non_matching_items(self):
        with patch.object(contracts_data, "ignore_list", ["* Blueprint"]):
            self.assertTrue(contracts_data.is_ignored("Ship Blueprint"))
            self.assertFalse(contracts_data.is_ignored("Ship"))

    def test_empty_region_does_not_require_contract_columns(self):
        with patch.object(contracts_data, "get_all_contracts", return_value=[]):
            contracts, items = contracts_data.get_all_contracts_from_region("Genesis", False, [])
        self.assertTrue(contracts.empty)
        self.assertTrue(items.empty)

    def test_mid_range_profit_gets_embed_without_extra_ping(self):
        with patch.object(contracts_data, "send_discord_message") as message:
            embed = contracts_data.format_discord_embed(
                0.3, "30.0%", 60_000_000, "60 million", 10, "10.00", "10", "Domain", 1,
                "140,000,000", "60,000,000", "1 days", "200,000,000", "Item", 0, "",
            )
        self.assertEqual(embed.color, contracts_data.discord.Color.blue())
        message.assert_not_called()

    def test_discord_messages_reuse_one_http_session(self):
        webhook = MagicMock()
        with patch.object(contracts_data, "discord_webhook_url", "https://discord.com/api/webhooks/1/token"), \
                patch.object(contracts_data.discord.SyncWebhook, "from_url", return_value=webhook) as from_url:
            contracts_data.send_discord_message("one")
            contracts_data.send_embed(None, contracts_data.Embed(title="two"))
        for call in from_url.call_args_list:
            self.assertIs(call.kwargs["session"], contracts_data.discord_session)
        self.assertEqual(webhook.send.call_count, 2)


class BrowserTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        with self.engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE contracts (
                    contract_id INTEGER, price REAL, jita_buy_value REAL,
                    total_material_price REAL, date_issued TEXT, region_name TEXT,
                    packaged_volume REAL, top_item_name TEXT, date_discovered TEXT,
                    date_expired TEXT, status TEXT, contains_unpublished INTEGER,
                    unpublished_items TEXT
                )
            """))
            connection.execute(text("""
                INSERT INTO contracts VALUES
                (123, 10, 100, NULL, '2026-01-01', 'The Forge', 5,
                 '<script>alert(1)</script>', '2026-01-02', '2026-01-30', 'active', 0, ''),
                (456, 0, 100, 0, '2026-01-01', 'Domain', 50,
                 'Ship Blueprint', '2026-01-02', '2026-01-30', 'expired', 0, ''),
                (789, 500, 0, NULL, '2026-01-01', 'Genesis', 1,
                 NULL, '2026-01-03', '2026-01-30', 'active', 1, 'Secret 100% Item')
            """))
            connection.execute(text("""
                CREATE TABLE contract_items (
                    contract_id INTEGER, row_id INTEGER, type_name TEXT,
                    quantity INTEGER, is_blueprint_copy INTEGER, runs INTEGER,
                    total_price REAL, total_material_price REAL
                )
            """))
            connection.execute(text("""
                INSERT INTO contract_items (contract_id, row_id, type_name) VALUES
                (123, 0, 'Tritanium'), (123, 1, 'Pyerite'), (789, 0, 'Secret 100% Item')
            """))
        self.patcher = patch.object(contract_browser, "engine", self.engine)
        self.patcher.start()
        self.client = contract_browser.app.test_client()

    def tearDown(self):
        self.patcher.stop()
        self.engine.dispose()

    def test_filters_are_bound_and_results_are_html_escaped(self):
        response = self.client.get("/?days=0&min_profit=90&max_volume=5")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"&lt;script&gt;", response.data)
        self.assertNotIn(b"<script>alert", response.data)
        response = self.client.get("/", query_string={
            "days": "0", "selected_region": "' OR 1=1 --",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No matching contracts", response.data)

    def test_rejects_invalid_numeric_filters(self):
        for value in ("nan", "inf", "-1", "1 OR 1=1"):
            with self.subTest(value=value):
                self.assertEqual(self.client.get("/", query_string={"min_profit": value}).status_code, 400)

    def test_expired_zero_price_and_blueprint_filters(self):
        response = self.client.get("/?days=0&status=expired")
        self.assertIn(b"Free", response.data)
        self.assertIn(b"Ship Blueprint", response.data)
        response = self.client.get("/?days=0&status=all&all_blueprints=1")
        self.assertNotIn(b"Ship Blueprint", response.data)

    def test_contents_empty_missing_and_invalid_ids(self):
        self.assertIn(b"No saved contents", self.client.get("/view_contract/456").data)
        self.assertEqual(self.client.get("/view_contract/999").status_code, 404)
        self.assertEqual(self.client.get("/view_contract/1%20OR%201=1").status_code, 404)
        self.assertEqual(self.client.get("/healthz").json, {"status": "ok"})

    def test_pagination_and_legacy_filter_redirect_preserve_only_known_filters(self):
        original = pd.read_sql_query("SELECT * FROM contracts WHERE contract_id = 123", self.engine)
        rows = [dict(original.iloc[0], contract_id=1000 + index) for index in range(100)]
        pd.DataFrame(rows).to_sql("contracts", self.engine, if_exists="append", index=False)
        response = self.client.get("/?days=0&selected_region=The+Forge&_external=1")
        self.assertEqual(response.data.count(b"/view_contract/"), 100)
        self.assertIn(b"page=2", response.data)
        response = self.client.get("/?days=0&selected_region=The+Forge&page=2")
        self.assertEqual(response.data.count(b"/view_contract/"), 1)
        response = self.client.post("/filter_contracts", data={
            "selected_region": "The Forge", "_external": "1", "endpoint": "health",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/?selected_region=The+Forge")

    def contract_ids(self, **query):
        response = self.client.get("/", query_string={"days": "0", "status": "all", **query})
        self.assertEqual(response.status_code, 200)
        return [int(i) for i in re.findall(rb"/view_contract/(\d+)", response.data)]

    def test_sorting_by_column_and_direction(self):
        self.assertEqual(self.contract_ids(sort="price", order="asc"), [456, 123])
        self.assertEqual(self.contract_ids(sort="price", order="desc"), [123, 456])
        self.assertEqual(self.contract_ids(sort="roi", order="desc"), [456, 123])  # free first
        # NULL material cost sorts last in both directions.
        self.assertEqual(self.contract_ids(sort="material", order="asc"), [456, 123])
        self.assertEqual(self.contract_ids(sort="material", order="desc"), [456, 123])
        for query in ({"sort": "price; DROP TABLE contracts"}, {"sort": "price", "order": "sideways"}):
            with self.subTest(query=query):
                self.assertEqual(self.client.get("/", query_string=query).status_code, 400)

    def test_header_links_toggle_order_and_keep_filters(self):
        response = self.client.get("/?days=0&item=trit&sort=price&order=asc")
        html = response.data.decode()
        self.assertIn('href="/?days=0&amp;item=trit&amp;sort=price&amp;order=desc"', html)
        self.assertIn('href="/?days=0&amp;item=trit&amp;sort=region&amp;order=asc"', html)
        self.assertIn('aria-sort="ascending"', html)

    def test_item_search_matches_any_item_and_treats_wildcards_literally(self):
        self.assertEqual(self.contract_ids(item="pyer"), [123])
        self.assertEqual(self.contract_ids(item="blueprint"), [456])
        self.assertEqual(self.contract_ids(item="%"), [])
        self.assertEqual(self.client.get("/", query_string={"item": "x" * 101}).status_code, 400)

    def test_unpublished_toggle_includes_unprofitable_contracts(self):
        self.assertNotIn(789, self.contract_ids())
        self.assertEqual(self.contract_ids(unpublished="1"), [789])
        self.assertEqual(self.contract_ids(unpublished="1", item="100%"), [789])
        self.assertIn(b"Unpublished: Secret 100% Item", self.client.get("/?days=0&unpublished=1").data)


if __name__ == "__main__":
    unittest.main()

import math
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, redirect, render_template, request, url_for
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

app = Flask(
    __name__, template_folder="render/contract_browser",
    static_folder="render/contract_browser/static",
)
load_dotenv()
engine = create_engine(URL.create(
    "mysql+pymysql", username=os.getenv("mysql_user"),
    password=os.getenv("mysql_password"), host=os.getenv("mysql_host"),
    database=os.getenv("mysql_database"),
), pool_pre_ping=True)
PAGE_SIZE = 100
FILTER_FIELDS = ("selected_region", "min_profit", "max_volume", "all_blueprints", "status", "days")


@app.template_filter("format_number")
def format_number(value):
    return "-" if pd.isna(value) else f"{value:,.0f}"


def number_filter(name):
    value = request.args.get(name, "").strip()
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        abort(400, description=f"{name} must be a non-negative number")
    if not math.isfinite(number) or number < 0:
        abort(400, description=f"{name} must be a finite, non-negative number")
    return number


@app.get("/healthz")
def health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return jsonify(status="ok")


@app.get("/")
def index():
    filters = ["price < jita_buy_value"]
    params = {}
    status = request.args.get("status", "active")
    if status not in ("active", "expired", "all"):
        abort(400, description="Unknown contract status")
    if status != "all":
        filters.append("status = :status")
        params["status"] = status
    region = request.args.get("selected_region", "").strip()
    if region:
        filters.append("region_name = :region")
        params["region"] = region
    for field, column, comparison in (
        ("min_profit", "(jita_buy_value - price)", ">="),
        ("max_volume", "packaged_volume", "<="),
    ):
        value = number_filter(field)
        if value is not None:
            filters.append(f"{column} {comparison} :{field}")
            params[field] = value
    if request.args.get("all_blueprints"):
        filters.append("LOWER(COALESCE(top_item_name, '')) NOT LIKE :blueprints")
        params["blueprints"] = "%blueprint%"
    days = request.args.get("days", "7")
    if days not in ("0", "7", "30"):
        abort(400, description="Unknown discovery period")
    if days != "0":
        filters.append("date_discovered >= :discovered_after")
        params["discovered_after"] = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=int(days))
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        abort(400, description="Page must be a positive integer")
    if page < 1:
        abort(400, description="Page must be a positive integer")
    params.update(limit=PAGE_SIZE + 1, offset=(page - 1) * PAGE_SIZE)
    query = text(f"""
        SELECT contract_id, price, jita_buy_value, total_material_price,
               date_issued, region_name, packaged_volume, top_item_name,
               date_discovered, status
        FROM contracts WHERE {' AND '.join(filters)}
        ORDER BY date_discovered DESC, contract_id DESC
        LIMIT :limit OFFSET :offset
    """)
    result = pd.read_sql_query(query, con=engine, params=params)
    has_next = len(result) > PAGE_SIZE
    result = result.iloc[:PAGE_SIZE].copy()
    result["profit"] = result["jita_buy_value"] - result["price"]
    links = {key: request.args[key] for key in FILTER_FIELDS if key in request.args}
    return render_template(
        "index.html", result=result.to_dict("records"), page=page,
        previous_url=url_for("index", **links, page=page - 1) if page > 1 else None,
        next_url=url_for("index", **links, page=page + 1) if has_next else None,
    )


@app.post("/filter_contracts")
def filter_contracts():
    filters = {key: request.form[key] for key in FILTER_FIELDS if key in request.form}
    return redirect(url_for("index", **filters))


@app.get("/view_contract/<int:contract_id>")
def view_contract(contract_id):
    info = pd.read_sql_query(text("""
        SELECT contract_id, price, jita_buy_value, region_name, date_issued,
               date_discovered, date_expired, status
        FROM contracts WHERE contract_id = :contract_id
    """), con=engine, params={"contract_id": contract_id})
    if info.empty:
        abort(404, description="Contract not found")
    items = pd.read_sql_query(text("""
        SELECT type_name, quantity, is_blueprint_copy, runs, total_price,
               total_material_price
        FROM contract_items WHERE contract_id = :contract_id ORDER BY row_id
    """), con=engine, params={"contract_id": contract_id})
    return render_template(
        "view_contract.html", contract=info.to_dict("records")[0],
        items=items.to_dict("records"),
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5003)

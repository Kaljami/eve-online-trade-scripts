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
FILTER_FIELDS = (
    "selected_region", "min_profit", "max_volume", "all_blueprints", "status", "days",
    "item", "unpublished", "sort", "order",
)
# Column key -> (SQL expression, default direction when first clicked)
SORT_COLUMNS = {
    "contract": ("contract_id", "desc"),
    "item": ("top_item_name", "asc"),
    "region": ("region_name", "asc"),
    "price": ("price", "desc"),
    "jita_buy": ("jita_buy_value", "desc"),
    "profit": ("(jita_buy_value - price)", "desc"),
    # Free contracts have unlimited ROI, so they sort above every priced contract.
    "roi": ("CASE WHEN price > 0 THEN (jita_buy_value - price) / price ELSE 1e18 END", "desc"),
    "material": ("total_material_price", "desc"),
    "volume": ("packaged_volume", "asc"),
    "status": ("status", "asc"),
    "discovered": ("date_discovered", "desc"),
}
DEFAULT_SORT = "discovered"
MAX_SEARCH_LENGTH = 100


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


def like_pattern(value):
    escaped = value.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return f"%{escaped}%"


@app.get("/")
def index():
    params = {}
    if request.args.get("unpublished"):
        # Unpublished items usually have no market value, so don't also require a Jita profit.
        filters = ["contains_unpublished > 0"]
    else:
        filters = ["price < jita_buy_value"]
    item = request.args.get("item", "").strip()
    if len(item) > MAX_SEARCH_LENGTH:
        abort(400, description=f"Item search must be at most {MAX_SEARCH_LENGTH} characters")
    if item:
        filters.append("""(
            top_item_name LIKE :item ESCAPE '!'
            OR EXISTS (
                SELECT 1 FROM contract_items
                WHERE contract_items.contract_id = contracts.contract_id
                AND contract_items.type_name LIKE :item ESCAPE '!'
            )
        )""")
        params["item"] = like_pattern(item)
    sort = request.args.get("sort", DEFAULT_SORT)
    if sort not in SORT_COLUMNS:
        abort(400, description="Unknown sort column")
    order = request.args.get("order", SORT_COLUMNS[sort][1])
    if order not in ("asc", "desc"):
        abort(400, description="Sort order must be asc or desc")
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
    sort_expression = SORT_COLUMNS[sort][0]
    # Only whitelisted expressions reach the SQL. Missing values go last in either direction.
    query = text(f"""
        SELECT contract_id, price, jita_buy_value, total_material_price,
               date_issued, region_name, packaged_volume, top_item_name,
               date_discovered, status, contains_unpublished, unpublished_items
        FROM contracts WHERE {' AND '.join(filters)}
        ORDER BY {sort_expression} IS NULL, {sort_expression} {order.upper()}, contract_id DESC
        LIMIT :limit OFFSET :offset
    """)
    result = pd.read_sql_query(query, con=engine, params=params)
    has_next = len(result) > PAGE_SIZE
    result = result.iloc[:PAGE_SIZE].copy()
    result["profit"] = result["jita_buy_value"] - result["price"]
    links = {key: request.args[key] for key in FILTER_FIELDS if key in request.args}
    sort_links = {}
    for key, (_, default_order) in SORT_COLUMNS.items():
        next_order = ("asc" if order == "desc" else "desc") if key == sort else default_order
        sort_links[key] = url_for("index", **{**links, "sort": key, "order": next_order})
    return render_template(
        "index.html", result=result.to_dict("records"), page=page,
        sort=sort, order=order, sort_links=sort_links,
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

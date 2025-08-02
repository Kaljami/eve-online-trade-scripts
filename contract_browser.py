from flask import Flask, render_template, request, redirect, url_for, jsonify
import pandas as pd
from io import StringIO
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from data_retrieval.sso_utils import reuse_oauth_session, get_character

app = Flask(__name__, template_folder='./render/contract_browser', static_folder='./render/contract_browser/static', )
load_dotenv()
# MySQL Database:
db_user = os.getenv("mysql_user")
db_password = os.getenv("mysql_password")
db_host = os.getenv("mysql_host")
db_database = os.getenv("mysql_database")
temp_character_id = 94653348

engine = create_engine(f'mysql+pymysql://{db_user}:{db_password}@{db_host}/{db_database}')
pd.options.display.float_format = '{:.0f}'.format # disable scientific notation
def format_number(value):
    return "{:,.0f}".format(value)
app.jinja_env.filters['format_number'] = format_number

### Index
@app.route('/')
def index(query_filter=''):
    print(query_filter)
    current_timestamp = datetime.now(timezone.utc)
    query = f"""
    SELECT *
    FROM (
        SELECT contract_id, price, start_location_id, jita_buy_value, date_issued, region_name, packaged_volume, total_material_price, top_item_name, date_discovered
        FROM contracts
        WHERE price < jita_buy_value AND status = 'active' {query_filter}
    ) AS recent_contracts
    WHERE date_discovered >= '{current_timestamp}' - INTERVAL 7 DAY;
    """
    result_df = pd.read_sql_query(query, con=engine)
    result_df['profit'] = result_df['jita_buy_value'] - result_df['price']
    result_df['profit_margin'] = result_df['profit'] / result_df['price']
    result_df['profit_margin_pct'] = result_df['profit_margin'].apply(lambda x: f"{x:.1%}")
    table = result_df.to_html(index=False)
    return render_template('index.html', table=table, result=result_df )

### Open contract in-game
@app.route('/open_contract/<contract_id>', methods=['GET'])
def open_contract(contract_id):
    sso_session = reuse_oauth_session(f'session_data_{temp_character_id}.json')
    print(f'logged in as { get_character(sso_session)}')
    url = f'https://esi.evetech.net/latest/ui/openwindow/contract/?contract_id={contract_id}'
    params = {}
    
    # Assuming sso_session is your authenticated session
    res = sso_session.post(url, params=params)
    
    if res.status_code == 200:
        return jsonify({"status": "success", "message": f"Contract {contract_id} opened successfully."})
    else:
        return jsonify({"status": "error", "message": f"Failed to open contract {contract_id}. Status code: {res.status_code}"}), 500

### Filtering the main listing
@app.route('/filter_contracts', methods=['POST'])
def filter_contracts():
    selected_region = request.form['selected_region']
    min_profit = request.form['min_profit']
    max_volume = request.form['max_volume']
    #if request.form['all_blueprints']: 
    if request.form.get('all_blueprints'): 
        ignore_all_blueprints = request.form['all_blueprints']
    else: 
        ignore_all_blueprints = False

    query_filter_options = []

    if selected_region:
        query_filter_options.append(f"AND region_name = '{selected_region}'")
    if min_profit:
        query_filter_options.append(f"AND jita_buy_value - price > {min_profit}")
    if max_volume:
        query_filter_options.append(f"AND packaged_volume < {max_volume}")
    if ignore_all_blueprints:
        query_filter_options.append(f"AND top_item_name NOT LIKE '%%blueprint%%'")

    query_filter = ' '.join(query_filter_options)
    print(query_filter)
    return index(query_filter)

### Viewing contract contents
@app.route('/view_contract/<contract_id>', methods=['GET'])
#@app.route('/view_contract', methods=['POST'])
def view_contract(contract_id):
    query = f"""
    SELECT type_name, quantity, is_blueprint_copy, total_price, total_material_price FROM contract_items WHERE contract_id = {contract_id};
    """
    query_info = f"""
    SELECT price, jita_buy_value, region_name, date_issued, date_discovered FROM contracts WHERE contract_id = {contract_id};
    """
    result_df = pd.read_sql_query(query, con=engine)
    result_html = result_df.to_html(table_id='contract_contents', index=False)
    info_df = pd.read_sql_query(query_info, con=engine)
    info_html = info_df.to_html(table_id='contract_contents', index=False)
    return render_template('view_contract.html', table=result_html, info_table=info_html, contract_id=contract_id)

if __name__ == '__main__':
    app.run(debug=True, port=5003)

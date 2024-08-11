from flask import Flask, render_template, request
import pandas as pd
from io import StringIO
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text

app = Flask(__name__, template_folder='./render/contract_browser', static_folder='./render/contract_browser/static', )
load_dotenv()
# MySQL Database:
db_user = os.getenv("mysql_user")
db_password = os.getenv("mysql_password")
db_host = os.getenv("mysql_host")
db_database = os.getenv("mysql_database")

engine = create_engine(f'mysql+pymysql://{db_user}:{db_password}@{db_host}/{db_database}')
pd.options.display.float_format = '{:.0f}'.format # disable scientific notation
def format_number(value):
    return "{:,.0f}".format(value)
    #return "{0:n}".format(value) # lol what scientific notation no thx 
    #return value
app.jinja_env.filters['format_number'] = format_number

@app.route('/')
def index():
    current_timestamp = datetime.now(timezone.utc)
    query = f"""
    SELECT *
    FROM (
        SELECT contract_id, price, start_location_id, jita_buy_value, date_issued, region_name, packaged_volume, top_item_name, date_discovered
        FROM contracts
        WHERE price < jita_buy_value
    ) AS recent_contracts
    WHERE date_discovered >= '{current_timestamp}' - INTERVAL 90 MINUTE;
    """
    result_df = pd.read_sql_query(query, con=engine)
    result_df['profit'] = result_df['jita_buy_value'] - result_df['price']
    result_df['profit_margin'] = result_df['profit'] / result_df['price']
    #result_df['profit_margin_pct'] = format(result_df['profit_margin'], ".1%")
    result_df['profit_margin_pct'] = result_df['profit_margin'].apply(lambda x: f"{x:.1%}")
    table = result_df.to_html(index=False)
    return render_template('index.html', table=table, result=result_df )

#@app.route('/process_data', methods=['POST'])


if __name__ == '__main__':
    app.run(debug=True, port=5003)

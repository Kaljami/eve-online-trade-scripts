# eve-online-trade-scripts

This is my fork of the original (abandoned) project by tomdml: https://github.com/tomdml/eve-online-trade-scanner

Original features (updated for current API version):
- Login with EVE Online account
- Market order update helper
- Cross-region trade calculator 

Features added:
- Saving login sessions
- Station trade calculator
- Automatic static data import from Fuzzworks dumps
- Contract scraper with configurable Discord notifications for profitable contracts (contracts_data.py)
    - Saves the contracts in MySQL database
    - Contract browser script for browser UI. Allows seeing expired and deleted contracts. 
- Ore and module reprocessing calculator 
- Stats collector script (pull_statistics.py)
    - Reads through character and/or corporation API data and saves a snapshot in MySQL and Influxdb 
    - Can be visualized in Grafana to track:
    - Net worth total and per character/corp
    - Asset value
    - Industry jobs
    - Outstanding and completed contracts
    - Mining amount (ISK)
    - Rats killed by type and bounty
- Multi-location appraisal tool (multi_appraisal.py)
    - Appraises the list of items at multiple different trade hubs and shows which is the cheapest for each item and total. 


## Probably outdated how-to-use
1. clone the repo
2. create a venv, activate and run pip install -r requirements.txt
3. register a new application in https://developers.eveonline.com/. (Enable API access and select all scopes for now since the project evolves alot.) Set the callback url to https://localhost/callback/. Add the Client ID and Secret key to a file as shown below. 
4. create .env file in the root of this repo and fill in the database and API details in the format shown below
5. download invVolumes.csv from latest fuzzworks dump and place it in static/
6. download eve SDE and place typeIDs.yaml in static/ (https://developers.eveonline.com/resource)
7. run python static/loader.py (will take a while to go through the 130mb file)
8. run main.py and add a character. Once logged in through the browser, copy the url (when you see the localhost, address not reachable) and paste it into terminal, press enter. To switch character, use the "Cycle SSO characters" function 
maybe create some empty folders when encountering a file or folder not found error, I probably forgot something. 

Tools: 
1. Find profitable items to haul between trade hubs, selectable buy or sell orders
2. Find good items for station trading in one location
3. Update current market orders quickly. Press V to open the next item to be updated on the market in-game, right click - modify order, CTRL+V to paste in the new lowest price. Only supports Jita at the moment. 


## .env setup 
Create a file in the root directory for the project and call it .env (no extension)
Copy the below lines and fill in your database settings. Influxdb is only needed for stats collection. Redis is used for caching market prices. If redis cannot be reached, caches will be saved on disk as pickles (slower).
```
influxdb_host = ''
influxdb_port = ''
influxdb_database = ''
influxdb_username = ''
influxdb_password = ''

EVE_CLIENT_ID = ''
EVE_CLIENT_SECRET = ''

stats_mysql_user = ''
stats_mysql_password = ''
stats_mysql_host = ''
stats_mysql_database = ''

mysql_user = ''
mysql_password = ''
mysql_host = ''
mysql_database = ''
mysql_database_fuzzworks = ''

redis_host = ''

discord_webhook_url = ''
discord_contract_notification_tag_id = ''
discord_sender_name = ''
discord_sender_icon_url = ''

ceo_character_ids = []
default_character_session_file = ''
```

To do for usability:
- Database table setup script
- Include Grafana dashboard 
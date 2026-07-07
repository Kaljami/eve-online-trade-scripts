### This is guaranteed to be out of date

import os

def create_directories_and_files():
    # Define directory and file names
    directories = ['sessions', 'sessions_stats', 'cache', 'logs']
    files = ['.env']
    env_content = """influxdb_host = ''
    influxdb_host = ''
    influxdb_port = ''
    influxdb_database = ''
    influxdb_username = ''
    influxdb_password = ''

    EVE_CLIENT_ID = ''
    EVE_CLIENT_SECRET = ''

    stats_mysql_user = 'eve_data'
    stats_mysql_password = 'set_your_own_password'
    stats_mysql_host = 'localhost'
    stats_mysql_database = 'eve_data'

    mysql_user = 'eve_data'
    mysql_password = 'set_your_own_password'
    mysql_host = 'localhost'
    mysql_database = 'eve_data'
    mysql_database_fuzzworks = 'eve_fuzz'

    redis_host = ''

    discord_webhook_url = ''
    discord_contract_notification_tag_id = ''
    discord_sender_name = ''
    discord_sender_icon_url = ''

    ceo_character_ids = []
    default_character_session_file = ''
    """

    # Create directories
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")

    # Create empty files
    for file in files:
        with open(file, 'w') as f:
            f.write(env_content)
            print(f"Created and populated file: {file}")

if __name__ == "__main__":
    create_directories_and_files()
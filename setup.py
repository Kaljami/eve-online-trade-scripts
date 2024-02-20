import os

def create_directories_and_files():
    # Define directory and file names
    directories = ['sessions', 'sessions_stats', 'cache', 'logs']
    files = ['keys_all_scopes.txt', 'influxdb_settings.txt']

    # Create directories
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")

    # Create empty files
    for file in files:
        with open(file, 'w') as f:
            print(f"Created empty file: {file}")

if __name__ == "__main__":
    create_directories_and_files()
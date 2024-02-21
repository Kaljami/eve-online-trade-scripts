import webbrowser
import os
import json
from requests_oauthlib import OAuth2Session
from dotenv import load_dotenv

### This is a shitshow and needs to be cleaned up

#SESSION_FILE = 'session_data.json'
#char_id = 0
#SESSION_FILE = f'sessions/session_data_{char_id}.json'
sessions_directory = 'sessions'
sessions_directory_stats = 'sessions_stats'

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = 'True' # seriously don't do this lol. Possibly throws an error because it tries to open the callback url https://localhost but there's no certificate? 

load_dotenv()


CLIENT_ID = os.getenv("EVE_CLIENT_ID")
CLIENT_SECRET = os.getenv("EVE_CLIENT_SECRET")

if CLIENT_ID and CLIENT_SECRET:
    print("CLIENT_ID and CLIENT_SECRET found, proceeding.")
else:
    print("Error: Missing SSO client keys in the file .env (maybe)")


def read_session_data(sessions_directory):
    session_files = [f for f in os.listdir(sessions_directory) if f.endswith('.json')]
    #for input_file in session_files:
        #file_path = os.path.join(sessions_directory, input_file)
    if len(session_files) > 0:
        file_path = f'{sessions_directory}/{session_files[0]}'
    try:
        with open(file_path, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return None
    except Exception as e:
        print (e)
        print ("Saved token was invalid, logging in again")
        return False

def cycle_sessions(sessions_directory):
    session_files = [f for f in os.listdir(sessions_directory) if f.endswith('.json')]
    #for input_file in session_files:
        #file_path = os.path.join(sessions_directory, input_file)
    if len(session_files) > 0:
        picked_session_id = input('Enter character index: ')
        try:
            picked_session_id = int(picked_session_id)
            print ("picked:",picked_session_id)
            picked_file = session_files[picked_session_id]
            file_path = f'{sessions_directory}/{picked_file}'
        except Exception as e:
            print('Error with input.', e)
            return False
    
    
    try:
        with open(file_path, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return None
    except Exception as e:
        print (e)
        print ("Saved token was invalid, logging in again")
        return False
    
def temp_dont_cycle_sessions(session_file):
    session_files = [f for f in os.listdir(sessions_directory_stats) if f.endswith('.json')]
    if len(session_files) > 0:
        session_file
        try:
            #picked_session_id = int(picked_session_id)
            #print ("picked:",picked_session_id)
            picked_file = session_file
            file_path = f'{sessions_directory_stats}/{picked_file}'
        except Exception as e:
            print('Error with input.', e)
            return False
    
    
    try:
        with open(file_path, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return None
    except Exception as e:
        print (e)
        print ("Saved token was invalid, logging in again")
        return False


def save_session_data(session_data, char_id):
    file_path = f'sessions/session_data_{char_id}.json'
    with open(file_path, 'w') as file:
        json.dump(session_data, file)



session_data = read_session_data(sessions_directory)

def oauth_session():
    def new_login():
        oauth = OAuth2Session(
            CLIENT_ID,
            redirect_uri='https://localhost/callback/',
            scope=[
                'publicData',
                'esi-calendar.respond_calendar_events.v1',
                'esi-calendar.read_calendar_events.v1',
                'esi-location.read_location.v1',
                'esi-location.read_ship_type.v1',
                'esi-mail.organize_mail.v1',
                'esi-mail.read_mail.v1',
                'esi-mail.send_mail.v1',
                'esi-skills.read_skills.v1',
                'esi-skills.read_skillqueue.v1',
                'esi-wallet.read_character_wallet.v1',
                'esi-wallet.read_corporation_wallet.v1',
                'esi-search.search_structures.v1',
                'esi-clones.read_clones.v1',
                'esi-characters.read_contacts.v1',
                'esi-universe.read_structures.v1',
                'esi-bookmarks.read_character_bookmarks.v1',
                'esi-killmails.read_killmails.v1',
                'esi-corporations.read_corporation_membership.v1',
                'esi-assets.read_assets.v1',
                'esi-planets.manage_planets.v1',
                'esi-fleets.read_fleet.v1',
                'esi-fleets.write_fleet.v1',
                'esi-ui.open_window.v1',
                'esi-ui.write_waypoint.v1',
                'esi-characters.write_contacts.v1',
                'esi-fittings.read_fittings.v1',
                'esi-fittings.write_fittings.v1',
                'esi-markets.structure_markets.v1',
                'esi-corporations.read_structures.v1',
                'esi-characters.read_loyalty.v1',
                'esi-characters.read_opportunities.v1',
                'esi-characters.read_chat_channels.v1',
                'esi-characters.read_medals.v1',
                'esi-characters.read_standings.v1',
                'esi-characters.read_agents_research.v1',
                'esi-industry.read_character_jobs.v1',
                'esi-markets.read_character_orders.v1',
                'esi-characters.read_blueprints.v1',
                'esi-characters.read_corporation_roles.v1',
                'esi-location.read_online.v1',
                'esi-contracts.read_character_contracts.v1',
                'esi-clones.read_implants.v1',
                'esi-characters.read_fatigue.v1',
                'esi-killmails.read_corporation_killmails.v1',
                'esi-corporations.track_members.v1',
                'esi-wallet.read_corporation_wallets.v1',
                'esi-characters.read_notifications.v1',
                'esi-corporations.read_divisions.v1',
                'esi-corporations.read_contacts.v1',
                'esi-assets.read_corporation_assets.v1',
                'esi-corporations.read_titles.v1',
                'esi-corporations.read_blueprints.v1',
                'esi-bookmarks.read_corporation_bookmarks.v1',
                'esi-contracts.read_corporation_contracts.v1',
                'esi-corporations.read_standings.v1',
                'esi-corporations.read_starbases.v1',
                'esi-industry.read_corporation_jobs.v1',
                'esi-markets.read_corporation_orders.v1',
                'esi-corporations.read_container_logs.v1',
                'esi-industry.read_character_mining.v1',
                'esi-industry.read_corporation_mining.v1',
                'esi-planets.read_customs_offices.v1',
                'esi-corporations.read_facilities.v1',
                'esi-corporations.read_medals.v1',
                'esi-characters.read_titles.v1',
                'esi-alliances.read_contacts.v1',
                'esi-characters.read_fw_stats.v1',
                'esi-corporations.read_fw_stats.v1',
                'esi-characterstats.read.v1',
            ]
        )

        auth_url, state = oauth.authorization_url('https://login.eveonline.com/oauth/authorize')
        webbrowser.open(auth_url)

        auth_response = input('Enter the callback URL > ')
        oauth.fetch_token(
                'https://login.eveonline.com/oauth/token',
                authorization_response=auth_response,
                client_secret=CLIENT_SECRET
            )
        # Save the session data for future use
        char_id = get_character_id(oauth)
        save_session_data(oauth.token, char_id) 
        return oauth



    if session_data:
        try:
            oauth = OAuth2Session(
                CLIENT_ID,
                token=session_data,
                redirect_uri='https://localhost/callback/',
                scope=[
                    'publicData',
                    'esi-calendar.respond_calendar_events.v1',
                    'esi-calendar.read_calendar_events.v1',
                    'esi-location.read_location.v1',
                    'esi-location.read_ship_type.v1',
                    'esi-mail.organize_mail.v1',
                    'esi-mail.read_mail.v1',
                    'esi-mail.send_mail.v1',
                    'esi-skills.read_skills.v1',
                    'esi-skills.read_skillqueue.v1',
                    'esi-wallet.read_character_wallet.v1',
                    'esi-wallet.read_corporation_wallet.v1',
                    'esi-search.search_structures.v1',
                    'esi-clones.read_clones.v1',
                    'esi-characters.read_contacts.v1',
                    'esi-universe.read_structures.v1',
                    'esi-bookmarks.read_character_bookmarks.v1',
                    'esi-killmails.read_killmails.v1',
                    'esi-corporations.read_corporation_membership.v1',
                    'esi-assets.read_assets.v1',
                    'esi-planets.manage_planets.v1',
                    'esi-fleets.read_fleet.v1',
                    'esi-fleets.write_fleet.v1',
                    'esi-ui.open_window.v1',
                    'esi-ui.write_waypoint.v1',
                    'esi-characters.write_contacts.v1',
                    'esi-fittings.read_fittings.v1',
                    'esi-fittings.write_fittings.v1',
                    'esi-markets.structure_markets.v1',
                    'esi-corporations.read_structures.v1',
                    'esi-characters.read_loyalty.v1',
                    'esi-characters.read_opportunities.v1',
                    'esi-characters.read_chat_channels.v1',
                    'esi-characters.read_medals.v1',
                    'esi-characters.read_standings.v1',
                    'esi-characters.read_agents_research.v1',
                    'esi-industry.read_character_jobs.v1',
                    'esi-markets.read_character_orders.v1',
                    'esi-characters.read_blueprints.v1',
                    'esi-characters.read_corporation_roles.v1',
                    'esi-location.read_online.v1',
                    'esi-contracts.read_character_contracts.v1',
                    'esi-clones.read_implants.v1',
                    'esi-characters.read_fatigue.v1',
                    'esi-killmails.read_corporation_killmails.v1',
                    'esi-corporations.track_members.v1',
                    'esi-wallet.read_corporation_wallets.v1',
                    'esi-characters.read_notifications.v1',
                    'esi-corporations.read_divisions.v1',
                    'esi-corporations.read_contacts.v1',
                    'esi-assets.read_corporation_assets.v1',
                    'esi-corporations.read_titles.v1',
                    'esi-corporations.read_blueprints.v1',
                    'esi-bookmarks.read_corporation_bookmarks.v1',
                    'esi-contracts.read_corporation_contracts.v1',
                    'esi-corporations.read_standings.v1',
                    'esi-corporations.read_starbases.v1',
                    'esi-industry.read_corporation_jobs.v1',
                    'esi-markets.read_corporation_orders.v1',
                    'esi-corporations.read_container_logs.v1',
                    'esi-industry.read_character_mining.v1',
                    'esi-industry.read_corporation_mining.v1',
                    'esi-planets.read_customs_offices.v1',
                    'esi-corporations.read_facilities.v1',
                    'esi-corporations.read_medals.v1',
                    'esi-characters.read_titles.v1',
                    'esi-alliances.read_contacts.v1',
                    'esi-characters.read_fw_stats.v1',
                    'esi-corporations.read_fw_stats.v1',
                    'esi-characterstats.read.v1',
                ]
            )
            oauth.refresh_token(
                    'https://login.eveonline.com/oauth/token',
                    refresh_token=oauth.token['refresh_token'],
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET
            )
            print ("Logged in using cached token")
            char_id = get_character_id(oauth)
            save_session_data(oauth.token, char_id) #save refreshed token
        except Exception as e:
            print (e)
            oauth = new_login()
    else:
        oauth = new_login()

    return oauth

def cycle_oauth_session():
    #picked_session_id = input(' > ')
    #print ("picked:",picked_session_id)
    session_data = cycle_sessions(sessions_directory)
    if session_data:
        try:
            oauth = OAuth2Session(
                CLIENT_ID,
                token=session_data,
                redirect_uri='https://localhost/callback/',
                scope=[
                    'publicData',
                    'esi-skills.read_skills.v1',
                    'esi-wallet.read_character_wallet.v1',
                    'esi-ui.open_window.v1',
                    'esi-markets.structure_markets.v1',
                    'esi-markets.read_character_orders.v1',
                    'esi-markets.read_corporation_orders.v1',
                ]
            )
            oauth.refresh_token(
                    'https://login.eveonline.com/oauth/token',
                    refresh_token=oauth.token['refresh_token'],
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET
            )
            print ("Logged in using cached token")
            char_id = get_character_id(oauth)
            save_session_data(oauth.token, char_id) #save refreshed token
        except Exception as e:
            print (e)
    else:
        print ("Error selecting saved session")

    return oauth

def temp_test_oauth_session(session_file):
    #picked_session_id = input(' > ')
    #print ("picked:",picked_session_id)
    session_data = temp_dont_cycle_sessions(session_file)
    if session_data:
        try:
            oauth = OAuth2Session(
                CLIENT_ID,
                token=session_data,
                redirect_uri='https://localhost/callback/',
                scope=[
                    'publicData',
                    'esi-skills.read_skills.v1',
                    'esi-wallet.read_character_wallet.v1',
                    'esi-ui.open_window.v1',
                    'esi-markets.structure_markets.v1',
                    'esi-markets.read_character_orders.v1',
                    'esi-markets.read_corporation_orders.v1',
                ]
            )
            oauth.refresh_token(
                    'https://login.eveonline.com/oauth/token',
                    refresh_token=oauth.token['refresh_token'],
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET
            )
            print ("Logged in using cached token")
            char_id = get_character_id(oauth)
            save_session_data(oauth.token, char_id) #save refreshed token
        except Exception as e:
            print (e)
    else:
        print ("Error selecting saved session")

    return oauth

def new_login():
        oauth = OAuth2Session(
            CLIENT_ID,
            redirect_uri='https://localhost/callback/',
            scope=[
                'publicData',
                'esi-calendar.respond_calendar_events.v1',
                'esi-calendar.read_calendar_events.v1',
                'esi-location.read_location.v1',
                'esi-location.read_ship_type.v1',
                'esi-mail.organize_mail.v1',
                'esi-mail.read_mail.v1',
                'esi-mail.send_mail.v1',
                'esi-skills.read_skills.v1',
                'esi-skills.read_skillqueue.v1',
                'esi-wallet.read_character_wallet.v1',
                'esi-wallet.read_corporation_wallet.v1',
                'esi-search.search_structures.v1',
                'esi-clones.read_clones.v1',
                'esi-characters.read_contacts.v1',
                'esi-universe.read_structures.v1',
                'esi-bookmarks.read_character_bookmarks.v1',
                'esi-killmails.read_killmails.v1',
                'esi-corporations.read_corporation_membership.v1',
                'esi-assets.read_assets.v1',
                'esi-planets.manage_planets.v1',
                'esi-fleets.read_fleet.v1',
                'esi-fleets.write_fleet.v1',
                'esi-ui.open_window.v1',
                'esi-ui.write_waypoint.v1',
                'esi-characters.write_contacts.v1',
                'esi-fittings.read_fittings.v1',
                'esi-fittings.write_fittings.v1',
                'esi-markets.structure_markets.v1',
                'esi-corporations.read_structures.v1',
                'esi-characters.read_loyalty.v1',
                'esi-characters.read_opportunities.v1',
                'esi-characters.read_chat_channels.v1',
                'esi-characters.read_medals.v1',
                'esi-characters.read_standings.v1',
                'esi-characters.read_agents_research.v1',
                'esi-industry.read_character_jobs.v1',
                'esi-markets.read_character_orders.v1',
                'esi-characters.read_blueprints.v1',
                'esi-characters.read_corporation_roles.v1',
                'esi-location.read_online.v1',
                'esi-contracts.read_character_contracts.v1',
                'esi-clones.read_implants.v1',
                'esi-characters.read_fatigue.v1',
                'esi-killmails.read_corporation_killmails.v1',
                'esi-corporations.track_members.v1',
                'esi-wallet.read_corporation_wallets.v1',
                'esi-characters.read_notifications.v1',
                'esi-corporations.read_divisions.v1',
                'esi-corporations.read_contacts.v1',
                'esi-assets.read_corporation_assets.v1',
                'esi-corporations.read_titles.v1',
                'esi-corporations.read_blueprints.v1',
                'esi-bookmarks.read_corporation_bookmarks.v1',
                'esi-contracts.read_corporation_contracts.v1',
                'esi-corporations.read_standings.v1',
                'esi-corporations.read_starbases.v1',
                'esi-industry.read_corporation_jobs.v1',
                'esi-markets.read_corporation_orders.v1',
                'esi-corporations.read_container_logs.v1',
                'esi-industry.read_character_mining.v1',
                'esi-industry.read_corporation_mining.v1',
                'esi-planets.read_customs_offices.v1',
                'esi-corporations.read_facilities.v1',
                'esi-corporations.read_medals.v1',
                'esi-characters.read_titles.v1',
                'esi-alliances.read_contacts.v1',
                'esi-characters.read_fw_stats.v1',
                'esi-corporations.read_fw_stats.v1',
                'esi-characterstats.read.v1',
            ]
        )

        auth_url, state = oauth.authorization_url('https://login.eveonline.com/oauth/authorize')
        #print(auth_url)
        webbrowser.open(auth_url)

        auth_response = input('Enter the callback URL > ')
        oauth.fetch_token(
                'https://login.eveonline.com/oauth/token',
                authorization_response=auth_response,
                client_secret=CLIENT_SECRET
            )
        # Save the session data for future use
        char_id = get_character_id(oauth)
        save_session_data(oauth.token, char_id) 
        return oauth

def get_character(session):
    if not session:
        return None

    res = session.get('https://login.eveonline.com/oauth/verify')
    return res.json()['CharacterName']

def get_character_id(session):
    if not session:
        return None

    res = session.get('https://login.eveonline.com/oauth/verify')
    return res.json()['CharacterID']
    

if __name__ == '__main__':
    session = oauth_session()
    print(f"Logged in as {get_character(session)}!")

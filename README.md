# eve-online-trade-scanner

This is my fork of the original by tomdml: https://github.com/tomdml/eve-online-trade-scanner


## Shitty how-to-use
1. clone the repo
2. create a venv, activate and run pip install -r requirements.txt
4. download invVolumes.csv from latest fuzzworks dump and place it in static/
5. download eve SDE and place typeIDs.yaml in static/ (https://developers.eveonline.com/resource)
6. run python static/loader.py (will take a while to go through the 130mb file)
7. register a new application in https://developers.eveonline.com/. (Enable API access and select all scopes for now since the project evolves a lot.) Set the callback url to https://localhost/callback/. Add the Client ID and Secret key to a file as shown below. 
8. run main.py and add a character. Once logged in through the browser, copy the url (when you see the localhost, address not reachable) and paste it into terminal, press enter. To switch character, use the "Cycle SSO characters" function 
maybe create some empty folders when encountering a file or folder not found error, I probably forgot something. 

Tools: 
1. Find profitable items to haul between trade hubs, selectable buy or sell orders
2. Find good items for station trading in one location
3. Update current market orders quickly. Press V to open the next item to be updated on the market in-game, right click - modify order, CTRL+V to paste in the new lowest price. Only supports Jita at the moment. 

pull_statistics.py:
Completely unrelated project to track wealth but shares some code so it lives here now.

## Where to shove the developer keys
Create a file in the root directory for the project and call it keys_all_scopes.txt
Add these two lines and replace xyz with your keys:
```
CLIENT_ID=xyz
CLIENT_SECRET=xyz
```

Below is the original readme:

---

EVE Online is a video game with a complex, player-driven economy. One of the key aspects of this economy is the market, where players can buy and sell items. Items do not automatically move when purchased, creating price differences across regions, which can be arbitraged.

This project uses OAuth2 and the EVE API to find profitable market trades across regions. It also contains a utility to rapidly update existing orders (In line with the EULA, of course).

You will need to register the application with CCP here: https://developers.eveonline.com/
There you will receive Client ID and Secret Key, which must be entered in keys.txt.

## Screenshots

Trade Finder Output

![Trade Finder output](https://i.imgur.com/RhXZ9h0.png)

Fast Order Update

https://i.imgur.com/UT2mcTq.mp4

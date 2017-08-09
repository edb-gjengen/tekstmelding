## Dependencies
	sudo apt install libmysqlclient-dev python-dev

## Setup environment
	$ python3 -m venv venv
	$ . venv/bin/activate
	(venv)$ pip install -U pip wheel
	(venv)$ pip install -r requirements.txt

## Create a config file
	$ cp config.py.sample config.py
	# Edit config.py with your favorite editor

## Create the database
	$ mysql -uUSER -p tekstmelding < create_db.sql

## Run the server
	(env)$ python tekstmelding.py

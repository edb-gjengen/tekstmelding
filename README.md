## Install:
	sudo apt install libmysqlclient-dev python-dev

	pyvenv env
	. env/bin/activate
	pip install -r requirements.txt

    # Create a config file:
	cp config.py.sample config.py
	# Edit config.py with your favorite editor

    # Create the database:
	mysql -uUSER -p tekstmelding < create_db.sql

    # Run the server:
	python tekstmelding.py

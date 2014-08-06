from flask import Flask
import MySQLdb
import MySQLdb.cursors
import datetime

import config

db = MySQLdb.connect(
	host	= config.DATABASE_HOST,
	user	= config.DATABASE_USER,
	passwd	= config.DATABASE_PASS,
	db		= config.DATABASE_NAME,
	cursorclass = MySQLdb.cursors.DictCursor)

cur = db.cursor()

app = Flask(__name__)

@app.route('/')
def main():
    return 'Tekstmelding er bezt!'

if __name__ == '__main__':
    app.run()

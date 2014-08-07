from flask import Flask, request
import MySQLdb
import MySQLdb.cursors
import datetime

import config

app = Flask(__name__)
app.config.from_object('config')

db = MySQLdb.connect(
	host	= app.config['DATABASE_HOST'],
	user	= app.config['DATABASE_USER'],
	passwd	= app.config['DATABASE_PASS'],
	db		= app.config['DATABASE_NAME'],
	cursorclass = MySQLdb.cursors.DictCursor)

cur = db.cursor()

@app.route('/')
def main():
	return 'Tekstmelding er bezt!'

@app.route('/callback')
def callback():
	gsm = request.args.get('gsm', None)
	operator = request.args.get('operator', None)
	kodeord = request.args.get('kodeord', None)
	tekst = request.args.get('tekst', None)
	kortnr = request.args.get('kortnr', None)
	ip = request.remote_addr

	return 'Got: %s' % (", ".join([('%s="%s"' % (k, v)) for k, v in request.args.items()]))

if __name__ == '__main__':
	app.run()

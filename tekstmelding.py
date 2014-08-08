from flask import Flask, request, g, abort
import MySQLdb
import MySQLdb.cursors
import datetime

import config

app = Flask(__name__)
app.config.from_object('config')

def connect_db():
	"""Connects to our database."""
	db = MySQLdb.connect(
		host    = app.config['DATABASE_HOST'],
		user    = app.config['DATABASE_USER'],
		passwd  = app.config['DATABASE_PASS'],
		db      = app.config['DATABASE_NAME'],
		cursorclass = MySQLdb.cursors.DictCursor)
	return db

def get_db():
	"""Opens a new database connection if there is none yet for the
	current application context."""
	if not hasattr(g, 'db'):
		g.db = connect_db()
	return g.db

@app.teardown_appcontext
def close_db(error):
	"""Closes the database again at the end of the request."""
	if hasattr(g, 'db'):
		g.db.close()

def query_db(query, args=(), one=False):
	"""Queries the database.

	Will use an existing or new database connection, create a cursor,
	execute the query, fetch all rows, close the cursor then return the rows.
	"""
	cur = get_db().cursor()
	if app.config['DEBUG']:
		app.logger.debug("Query: %s", query)
		app.logger.debug("Args: %s", args)
	cur.execute(query, args)
	rv = cur.fetchall()
	cur.close()
	return (rv[0] if rv else None) if one else rv

def get_user_by_phone(number):
	user = query_db("""
		SELECT user.*
		FROM din_user user, din_userphonenumber phone
		WHERE phone.number = %s AND
		      user.id = phone.user_id""",
		[number], one=True)
	return user

@app.route('/')
def main():
	return 'Tekstmelding er bezt!'

@app.route('/callback')
def callback():
	gsm      = request.args.get('gsm', None)
	operator = request.args.get('operator', None)
	kodeord  = request.args.get('kodeord', None)
	tekst    = request.args.get('tekst', None)
	kortnr   = request.args.get('kortnr', None)
	ip       = request.remote_addr

	if not gsm.isdigit():
		# What the fuck, man, that's not a phone number, man.
		abort(400) # Bad Request

	# We could use the country code from 'operator' here,
	# but can we can't receive messages from abroad. Right?
	user = get_user_by_phone("+47%s" % gsm)
	return str(user.items()) if user else 'None'

	#return 'Got: %s' % (", ".join([('%s="%s"' % (k, v)) for k, v in request.args.items()]))

if __name__ == '__main__':
	app.run()

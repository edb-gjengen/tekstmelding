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
		app.logger.debug("Query: %s\nArgs: %s", query, args)
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

def log_incoming(userid, gsm, codeword, message, operator, shortno, action, ip, simulation):
	query_db("""
		INSERT INTO din_sms_received
			(userid, gsm, codeword, message, operator, shortno, action, IP, simulation)
		VALUES
			(%s, %s, %s, %s, %s, %s, %s, %s, %s)
	""", [userid, gsm, codeword, message, operator, shortno, action, ip, simulation])

@app.route('/')
def main():
	return 'Tekstmelding er bezt!'

@app.route('/callback')
def callback():
	gsm      = request.args.get('gsm', None)
	operator = request.args.get('operator', None)
	codeword = request.args.get('kodeord', None)
	message  = request.args.get('tekst', None)
	shortno  = request.args.get('kortnr', None)
	ip       = request.remote_addr

	if not gsm.isdigit():
		# What the fuck, man, that's not a phone number, man.
		abort(400) # Bad Request

	# We could use the country code from 'operator' here,
	# but can we can't receive messages from operators. Right?
	user = get_user_by_phone("+47%s" % gsm)

	log_incoming(
		userid     = int(user['id']) if user else None,
		gsm        = gsm,
		codeword   = codeword,
		message    = message,
		operator   = operator,
		shortno    = shortno,
		action     = 'no_action',
		ip         = ip,
		simulation = 0)

	return str(user.items()) if user else 'None'

if __name__ == '__main__':
	app.run()

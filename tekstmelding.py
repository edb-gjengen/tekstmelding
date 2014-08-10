from flask import Flask, request, g, abort, jsonify
from utils import CustomJSONEncoder, generate_activation_code
import MySQLdb
import MySQLdb.cursors
import datetime

import config

app = Flask(__name__)
app.config.from_object('config')
app.json_encoder = CustomJSONEncoder

def connect_db():
	"""Connects to our database."""
	db = MySQLdb.connect(
		host    = app.config['DATABASE_HOST'],
		user    = app.config['DATABASE_USER'],
		passwd  = app.config['DATABASE_PASS'],
		db      = app.config['DATABASE_NAME'],
		cursorclass = MySQLdb.cursors.DictCursor,
		charset='utf8')
	return db

def get_db():
	"""Opens a new database connection if there is none yet for the
	current application context."""
	if not hasattr(g, 'db'):
		g.db = connect_db()
	return g.db

@app.teardown_appcontext
def close_db(error):
	"""Closes the database connection at the end of the request."""
	if hasattr(g, 'db'):
		g.db.close()

def query_db(query, args=(), one=False, lastrowid=False):
	"""Queries the database.

	Will use an existing or new database connection, create a cursor,
	execute the query, fetch all rows, close the cursor then return the rows.
	"""
	assert not (one and lastrowid)

	cur = get_db().cursor()
	app.logger.debug("Query: %s\nArgs: %s", query, args)
	cur.execute(query, args)

	if lastrowid:
	    ret = cur.lastrowid
	else:
	    rv = cur.fetchall()
	    ret = (rv[0] if rv else None) if one else rv
	cur.close()
	return ret

def get_user_by_phone(number):
	user = query_db("""
		SELECT user.*,
		       (CASE WHEN (user.expires IS NULL) THEN 1 ELSE 0 END) AS expires_lifelong
		FROM din_user user, din_userphonenumber phone
		WHERE phone.number = %s AND
		      user.id = phone.user_id
	""", [number], one=True)
	return user

def log_incoming(**kwargs):
	return query_db("""
		INSERT INTO din_sms_received
			(userid, gsm, codeword, message, operator, shortno, action, IP, simulation)
		VALUES
			(%(userid)s, %(gsm)s, %(codeword)s, %(message)s, %(operator)s, %(shortno)s, %(action)s, %(ip)s, %(simulation)s)
	""", kwargs, lastrowid=True)

def set_incoming_action(**kwargs):
	query_db("""
		UPDATE din_sms_received
		SET action = %(action)s
		WHERE smsid = %(smsid)s
	""", kwargs)

def log_sent(**kwargs):
	query_db("""
		INSERT INTO din_sms_sent
			(response_to, msgid, sender, receiver, countrycode, message, operator, codeword, billing_price, use_dlr, simulation, activation_code)
		VALUES
			(%(response_to)s, %(msgid)s, %(sender)s, %(receiver)s, %(countrycode)s, %(message)s,
			 %(operator)s, %(codeword)s, %(billing_price)s, %(use_dlr)s, %(simulation)s, %(activation_code)s)
	""", kwargs)

@app.route('/')
def main():
	return 'Tekstmelding er bezt!'

@app.route('/callback')
def callback():
	gsm      = request.args.get('gsm', None)
	operator = request.args.get('operator', None)
	codeword = request.args.get('kodeord', None)
	message  = request.args.get('tekst', '')
	shortno  = request.args.get('kortnr', None)
	ip       = request.remote_addr

	if None in (gsm, operator, codeword, shortno):
		abort(400) # Bad Request

	if not gsm.isdigit():
		# What the fuck, man, that's not a phone number, man.
		abort(400) # Bad Request

	if not codeword.strip().upper() in ('DNS', 'DNSMEDLEM'):
		abort(400) # Bad Request

	user = get_user_by_phone("+47%s" % gsm)

	id_incoming_sms = log_incoming(
		userid     = int(user['id']) if user else None,
		gsm        = gsm,
		codeword   = codeword,
		message    = message,
		operator   = operator,
		shortno    = shortno,
		action     = 'no_action',
		ip         = ip,
		simulation = 0)

	app.logger.info("Incoming SMS from gsm:%s saved with smsid:%s", gsm, id_incoming_sms)

	if codeword.strip().upper() == 'DNS':
		app.logger.info("Sent SMS to gsm:%s with payment options", gsm)
		set_incoming_action(smsid=id_incoming_sms, action='notify_payment_options')
		return 'notify_payment_options'

	# Past this point, codeword is DNSMEDLEM

	if user:
		# A friendly reminder about how the 'expires' column works:
		# 	NULL means the membership should never expire
		#	0000-00-00 is the default and means the user has never had a membership
		#	YYYY-MM-DD is the day the membership will or has expired
		#
		# datetime.date does not accept the date 0000-00-00, instead we end
		# up with None. As a workaround we do the NULL comparison with SQL
		# and store the result in 'expires_lifelong'.
		expires = user.get('expires', None)
		expires_lifelong = user.get('expires_lifelong', None)

		# Does this user have a lifelong membership?
		if expires_lifelong:
			app.logger.info("Membership of user_id:%s gsm:%s never expires", user['id'], gsm)
			set_incoming_action(smsid=id_incoming_sms, action='notify_already_a_member')

		# No need to renew non-expired memberships.
		elif type(expires) is datetime.date and expires >= datetime.date.today():
			app.logger.info("Membership of user_id:%s gsm:%s has not expired yet", user['id'], gsm)
			set_incoming_action(smsid=id_incoming_sms, action='notify_already_a_member')

		# Should we renew?
		elif not expires or (type(expires) is datetime.date and expires < datetime.date.today()):
			new_expire = datetime.date.today() + datetime.timedelta(days=365)
			app.logger.info("Membership of user_id:%s gsm:%s was renewed to %s", user['id'], gsm, new_expire)
			set_incoming_action(smsid=id_incoming_sms, action='renew_membership')

		else:
			assert False, "What a trainwreck, we shouldn't be here"

		return jsonify(user.items())
	else:
		app.logger.info("New membership for gsm:%s, activation code sent", gsm)
		set_incoming_action(smsid=id_incoming_sms, action='new_membership_send_code')
		result = {'result': 'No existing member.', 'action': 'new_membership_send_code'}
		activation_code = generate_activation_code()

		log_sent(
			response_to = id_incoming_sms,
			msgid = 1337,
			sender = 'dns',
			receiver = gsm,
			countrycode = operator[:1],
			message = "Velkommen! Dette er et midlertidig medlemsbevis. Aktiver medlemskapet ditt her: https://s.neuf.no/sms?n=%s&c=%s" % (gsm, activation_code),
			operator = operator,
			codeword = codeword,
			billing_price = 230 * 100,
			use_dlr = 0,
			simulation = 0,
			activation_code = activation_code)

		return jsonify(result)

@app.route('/dlr')
def dlr():
	return ''

if __name__ == '__main__':
	app.run()

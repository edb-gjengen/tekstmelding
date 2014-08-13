#!/usr/bin/env python
# -*- coding: utf-8 -*-

from flask import Flask, request, g, abort, jsonify
from utils import CustomJSONEncoder, generate_activation_code
import MySQLdb
import MySQLdb.cursors
import datetime
import requests
import sys

import config

app = Flask(__name__)
app.config.from_object('config')
app.json_encoder = CustomJSONEncoder

if not app.debug:
    import logging
    from logging.handlers import StreamHandler
    handler = StreamHandler(stream=sys.stderr)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)

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

	app.logger.debug("Query: %s\nArgs: %s", query, args)

	cur = get_db().cursor()
	cur.execute(query, args)

	if lastrowid:
	    ret = cur.lastrowid
	else:
	    rv = cur.fetchall()
	    ret = (rv[0] if rv else None) if one else rv

	get_db().commit()
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

def is_user_expired(user):
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

	# Lifelong membership?
	if expires_lifelong:
		return False

	# Non-expired membership?
	elif type(expires) is datetime.date and expires >= datetime.date.today():
		return False

	# Expired?
	elif not expires or (type(expires) is datetime.date and expires < datetime.date.today()):
		return True

	else:
		assert False, "What a trainwreck, we shouldn't be here"

def get_full_name(user):
	full_name = "%s %s" % (
		user.get('firstname', '').strip(),
		user.get('lastname', '').strip()
	)
	return full_name[:50].strip()

def fix_encoding(message):
	try:
		assert type(message) == unicode
		new_message = message.encode('latin-1', 'ignore')
	except:
		new_message = message
		app.logger.warning("Unicode woes: message_type=%s message=%s exc_info=%s",
			type(message), message, sys.exc_info())
		# Oh, never mind, let's try to send it anyway.
		pass

	return new_message

def send_sms(log_only=False, gsm=None, message=None, response_to=None, billing=False, billing_price=None, operator=None, activation_code=None):
	assert gsm
	assert message

	if billing:
		assert billing_price
		if not operator:
			operator = 'ukjent'

	# The strings in this file are in utf-8, encode to latin-1 before sending
	message_latin = fix_encoding(message)

	# Truncate message if too long
	if len(message_latin) > 160:
		app.logger.warning("Truncated the following message to 160 chars: %s", message_latin)
		message_latin = message_latin[:160]

	params = {
		'bruker': app.config['EB_USER'],
		'passord': app.config['EB_PASSWORD'],
		'avsender': app.config['EB_SENDER_BULK'],
		'land': 47,
		'til': gsm,
		'melding': message_latin,
	}

	if billing:
		params.update({
			'avsender': app.config['EB_SENDER_BILLING'],
			#'dlrurl': app.config['EB_DLR'],
			'ore': billing_price,
			'operator': operator,
			'kodeord': 'DNSMEDLEM',
		})

	if app.config['EB_SIMULATE']:
		params['simulate'] = 1

	app.logger.debug("send_sms params: %s" % params.items())

	msgid = 0

	if not log_only:
		endpoint = app.config['EB_PAYURL'] if billing else app.config['EB_URL']

		try:
			result = requests.get(endpoint, params=params)
		except:
			app.logger.error("Caught exception while attempting to contact Eurobate: %s", sys.exc_info())
			return False

		if result.status_code != requests.codes.ok: # 200
			app.logger.error("Got status code %s from Eurobate", result.status_code)
			return False

		app.logger.debug("Hit URL: %s\nGot result.text: %s", result.url, result.text)
		
		response = result.text.split(' ')
		if response[:3] == ['Meldingen', 'er', 'sendt']:
			if billing and len(response) == 4 and response[3].isdigit():
				msgid = int(response[3])
			if billing and msgid == 0:
				app.logger.warning("Did not get a msgid from Eurobate when billing as response to smsid:%s", response_to)
		else:
			app.logger.error("Message (response_to:%s) was not sent. Eurobate told us: %s", response_to, result.text)
			return False

	log_sent(
		response_to = response_to if response_to else 0,
		msgid = msgid if billing else 0,
		sender = params['avsender'],
		receiver = gsm,
		countrycode = params['land'],
		message = message,
		operator = params['operator'] if billing else 'NULL',
		codeword = params['kodeord'] if billing else 'NULL',
		billing_price = params['ore'] if billing else 0,
		#use_dlr = 1 if billing else 0,
		use_dlr = 0,
		simulation = 1 if app.config['EB_SIMULATE'] else 0,
		activation_code = activation_code if activation_code else 'NULL')

	return True if not billing else msgid

def notify_valid_membership(response_to=None, gsm=None, user=None):
	assert gsm and user

	message = u"Hei %(name)s! Ditt medlemskap er gyldig til %(expires)s. Last ned app: %(app_link)s" % ({
		'name': get_full_name(user),
		'expires': 'verdens undergang' if user.get('expires_lifelong') else str(user.get('expires')),
		'app_link': 'http://snappo.com/app',
	})

	send_sms(log_only=True, response_to=response_to, gsm=gsm, message=message)
	app.logger.info("Sent SMS to gsm:%s with proof of membership and link to app", gsm)
	set_incoming_action(smsid=response_to, action='notify_valid_membership')
	return fix_encoding(message)

def notify_payment_options_new(response_to=None, gsm=None):
	assert gsm

	message = u"Du kan kjøpe medlemskap via SnappOrder: http://snappo.com/app (200,-) eller ved å sende DNSMEDLEM til 2090 (230,-)"
	send_sms(log_only=True, response_to=response_to, gsm=gsm, message=message)
	app.logger.info("Sent SMS to gsm:%s with payment options (new)", gsm)
	set_incoming_action(smsid=response_to, action='notify_payment_options_new')
	return fix_encoding(message)

def notify_payment_options_renewal(response_to=None, gsm=None):
	assert gsm

	message = u"Ditt medlemskap er utløpt. Det kan fornyes via SnappOrder: http://snappo.com/app (200,-) eller ved å sende DNSMEDLEM til 2090 (230,-)"
	send_sms(log_only=True, response_to=response_to, gsm=gsm, message=message)
	app.logger.info("Sent SMS to gsm:%s with payment options (renewal)", gsm)
	set_incoming_action(smsid=response_to, action='notify_payment_options_renewal')
	return fix_encoding(message)

def notify_could_not_charge(response_to=None, gsm=None):
	assert gsm

	app.logger.warning("Attempt to charge gsm:%s as a response to smsid:%s failed", gsm, response_to)
	message = u"Beklager, bestillingen kunne ikke gjennomføres. Spørsmål? medlem@studentersamfundet.no"
	send_sms(log_only=True, response_to=response_to, gsm=gsm, message=message)
	set_incoming_action(smsid=response_to, action='notify_could_not_charge')
	return fix_encoding(message)

def renew_membership(response_to=None, gsm=None, user=None, operator=None):
	assert gsm and user

	new_expire = datetime.date.today() + datetime.timedelta(days=365)

	query_db(
		"UPDATE din_user SET expires = %(expires)s WHERE id = %(id)s", {
			'expires': str(new_expire),
			'id': user['id']
	})

	query_db("""
		INSERT INTO din_userupdate (date, user_id_updated, comment, user_id_updated_by)
		VALUES (%(date)s, %(user_id_updated)s, %(comment)s, %(user_id_updated_by)s)
	""", {
		'date': str(datetime.datetime.now()),
		'user_id_updated': user['id'],
		'comment': "Medlemskap fornyet med SMS.",
		'user_id_updated_by': user['id'],
	})

	message = u"Hei %(name)s! Ditt medlemskap er nå gyldig ut %(new_expire)s. Spørsmål? medlem@studentersamfundet.no" % ({
		'name': get_full_name(user),
		'new_expire': str(new_expire),
	})

	msgid = send_sms(
		response_to = response_to,
		gsm = gsm,
		message = message,
		operator = operator,
		billing = True,
		billing_price = app.config['MEMBERSHIP_PRICE_KR'] * 100,
	)

	if not msgid:
		return notify_could_not_charge(response_to=response_to, gsm=gsm)

	app.logger.info("Membership of user_id:%s gsm:%s was renewed to %s", user['id'], gsm, new_expire)
	set_incoming_action(smsid=response_to, action='renew_membership')
	return fix_encoding(u"Vi vil nå forsøke å fornye medlemskapet ditt...")

def new_membership(response_to=None, gsm=None, operator=None):
	assert gsm

	activation_code = generate_activation_code()

	message = u"Velkommen! Dette er et midlertidig medlemsbevis. Aktiver medlemskapet ditt her: http://s.neuf.no/sms/%(gsm)s/%(activation_code)s" % ({
		'gsm': gsm,
		'activation_code': activation_code,
	})

	msgid = send_sms(
		response_to = response_to,
		gsm = gsm,
		message = message,
		operator = operator,
		activation_code = activation_code,
		billing = True,
		billing_price = app.config['MEMBERSHIP_PRICE_KR'] * 100,
	)

	if not msgid:
		return notify_could_not_charge(response_to=response_to, gsm=gsm)

	app.logger.info("New membership for gsm:%s, activation code sent", gsm)
	set_incoming_action(smsid=response_to, action='new_membership')
	return fix_encoding(u"Vi vil nå forsøke å belaste deg for et medlemskap...")

@app.route('/')
def main():
	return 'Tekstmelding!'

@app.route('/callback')
def callback():
	gsm      = request.args.get('gsm', None)
	operator = request.args.get('operator', 'ukjent')
	codeword = request.args.get('kodeord', None)
	message  = request.args.get('tekst', '')
	shortno  = request.args.get('kortnr', None)
	ip       = request.remote_addr

	if None in (gsm, codeword, shortno):
		abort(400) # Bad Request

	if not gsm.isdigit():
		# What the fuck, man, that's not a phone number, man.
		abort(400) # Bad Request

	if not codeword.strip().upper() in ('DNS', 'DNSMEDLEM'):
		abort(400) # Bad Request

	user = get_user_by_phone("+47%s" % gsm)

	smsid = log_incoming(
		userid     = int(user['id']) if user else None,
		gsm        = gsm,
		codeword   = codeword,
		message    = message,
		operator   = operator,
		shortno    = shortno,
		action     = 'no_action',
		ip         = ip,
		simulation = 0)

	app.logger.info("Incoming SMS from gsm:%s saved with smsid:%s", gsm, smsid)

	if user:
		expired = is_user_expired(user)

		if codeword.strip().upper() == 'DNS':
			if not expired:
				return notify_valid_membership(response_to=smsid, gsm=gsm, user=user)
			elif expired:
				return notify_payment_options_renewal(response_to=smsid, gsm=gsm)
		elif codeword.strip().upper() == 'DNSMEDLEM':
			if not expired:
				return notify_valid_membership(response_to=smsid, gsm=gsm, user=user)
			elif expired:
				return renew_membership(response_to=smsid, gsm=gsm, user=user, operator=operator)
	else:
		if codeword.strip().upper() == 'DNS':
			return notify_payment_options_new(response_to=smsid, gsm=gsm)
		elif codeword.strip().upper() == 'DNSMEDLEM':
			return new_membership(response_to=smsid, gsm=gsm, operator=operator)

@app.route('/dlr')
def dlr():
	return ''

if __name__ == '__main__':
	app.run()

# For WSGI
application = app

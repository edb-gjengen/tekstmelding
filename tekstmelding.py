#!/usr/bin/env python
# -*- coding: utf-8 -*-
from flask import Flask, request, g, abort, jsonify, render_template
import MySQLdb
import MySQLdb.cursors
import datetime
import logging
import logging.config

from utils import require_token, MyJSONEncoder
import sendega
import dusken

import config

app = Flask(__name__)
app.config.from_object('config')
app.json_encoder = MyJSONEncoder

if not app.debug:
    logging.config.dictConfig(app.config['LOGGING'])


def connect_db():
    """Connects to our database."""
    db = MySQLdb.connect(
        host=app.config['DB_HOST'],
        user=app.config['DB_USER'],
        passwd=app.config['DB_PASS'],
        db=app.config['DB_NAME'],
        cursorclass=MySQLdb.cursors.DictCursor,
        charset='utf8')
    return db


def get_db():
    """Returns a database connection.
    Creates one if there is none for the current application context."""
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

    # app.logger.debug('Got query with args: %s', query, args)

    cur = get_db().cursor()
    cur.execute(query, args)

    # app.logger.debug('Executed query: %s', cur._last_executed)

    if lastrowid:
        ret = cur.lastrowid
    else:
        rv = cur.fetchall()
        ret = (rv[0] if rv else None) if one else rv

    get_db().commit()
    cur.close()
    return ret


def get_sendega():
    """Returns a Sendega object.
    Creates one if there is none for the current application context."""
    if not hasattr(g, 'sendega'):
        g.sendega = sendega.Sendega(
            wsdl=app.config['SENDEGA_WSDL'],
            username=app.config['SENDEGA_USERNAME'],
            password=app.config['SENDEGA_PASSWORD'],
            sender_bulk=app.config['SENDEGA_SENDER_BULK'],
            sender_billing=app.config['SENDEGA_SENDER_BILLING'],
            dlr_url=app.config['SENDEGA_DLR'])
    return g.sendega


def log_incoming(**kwargs):
    return query_db("""
        INSERT INTO incoming
            (msgid, msisdn, msg, mms, mmsdata, shortcode,
            mcc, mnc, pricegroup, keyword, keywordid,
            errorcode, errormessage, registered, ip)
        VALUES
            (%(msgid)s, %(msisdn)s, %(msg)s, %(mms)s, %(mmsdata)s, %(shortcode)s,
            %(mcc)s, %(mnc)s, %(pricegroup)s, %(keyword)s, %(keywordid)s,
            %(errorcode)s, %(errormessage)s, %(registered)s, %(ip)s)
    """, kwargs, lastrowid=True)


def log_outgoing(**kwargs):
    return query_db("""
        INSERT INTO outgoing
            (sender, destination, pricegroup, content,
            contentTypeID, contentHeader, dlrUrl,
            ageLimit, extID, sendDate, refID, priority,
            gwID, pid, dcs)
        VALUES
            (%(sender)s, %(destination)s, %(pricegroup)s, %(content)s,
            %(contentTypeID)s, %(contentHeader)s, %(dlrUrl)s,
            %(ageLimit)s, %(extID)s, %(sendDate)s, %(refID)s, %(priority)s,
            %(gwID)s, %(pid)s, %(dcs)s)
    """, kwargs, lastrowid=True)


def log_outgoing_response(**kwargs):
    return query_db("""
        INSERT INTO outgoing_response
            (id, MessageID, Success, ErrorNumber, ErrorMessage)
        VALUES
            (%(id)s, %(MessageID)s, %(Success)s, %(ErrorNumber)s, %(ErrorMessage)s)
    """, kwargs, lastrowid=True)


def log_event(**kwargs):
    for key in ('incoming_id', 'outgoing_id', 'dlr_id',
                'action', 'activation_code', 'user_id'):
        kwargs.setdefault(key, None)

    return query_db("""
        INSERT INTO event
            (incoming_id, outgoing_id, dlr_id,
            action, user_id, activation_code)
        VALUES
            (%(incoming_id)s, %(outgoing_id)s, %(dlr_id)s,
            %(action)s, %(user_id)s, %(activation_code)s)
    """, kwargs, lastrowid=True)


def update_event(event_id, outgoing_id):
    query_db(
        "UPDATE event SET outgoing_id=%s WHERE id=%s",
        [outgoing_id, event_id])


def send_sms(destination, content, incoming_id=None,
             billing=False, price=0, activation_code=None):
    args = get_sendega().create_sms(
        destination=destination,
        content=content,
        reference=incoming_id,
        billing=billing,
        price=price)

    app.logger.debug('Outgoing, args: %s', args)

    outgoing_id = log_outgoing(**args)

    if app.debug:
        return outgoing_id

    response = get_sendega().send(**args)
    response['id'] = outgoing_id
    log_outgoing_response(**response)

    if response.get('Success', None):
        return outgoing_id

    return None


def send_app_link(incoming_id=None, number=None):
    content = u"Last ned Chateau Neuf sin app her: %(app)s" % ({
        'app': 'https://app.neuf.no',
    })

    outgoing_id = send_sms(
        destination=number,
        content=content,
        incoming_id=incoming_id)

    app.logger.info("Sent SMS to number:%s with app_link", number)

    log_event(
        action='send_app_link',
        incoming_id=incoming_id,
        outgoing_id=outgoing_id)

    return 'OK'


@app.route('/send', methods=['POST'])
@require_token
def send():
    data = request.get_json()
    number = data.get('to')
    message = data.get('message')

    if not number or not message:
        return jsonify(**{'error': 'Missing required param number or message'}), 400

    if number[0] == '+':
        number = number.replace('+', '')

    if not number.isdigit():
        return jsonify(**{'error': "Param number is not numerical '{}'".format(number)}), 400

    app.logger.info('Sending to number={}, service={}, message={}'.format(
        number, g.user, message))

    outgoing_id = send_sms(destination=number, content=message)

    log_event(action='send', outgoing_id=outgoing_id)

    return jsonify(**{'result': 'sent', 'message': message, 'outgoing_id': outgoing_id})


@app.route('/sendega-incoming', methods=['POST'])
def incoming():
    args = {'ip': request.headers.get('X-Real-IP') or request.remote_addr}

    for key in ('msgid', 'msisdn', 'msg', 'mms', 'mmsdata', 'shortcode',
                'mcc', 'mnc', 'pricegroup', 'keyword', 'keywordid',
                'errorcode', 'errormessage', 'registered'):
        args[key] = request.form.get(key)

    app.logger.debug("Incoming, args: %s", args)

    if None in (args['msisdn'], args['keyword'], args['shortcode']):
        abort(400)  # Bad Request

    msisdn = args['msisdn']
    keyword = args['keyword'].strip().upper()
    shortcode = args['shortcode']

    if not msisdn.isdigit():
        # What the fuck, man, that's not a phone number, man.
        abort(400)  # Bad Request

    if keyword not in ('DNS', 'DNSMEDLEM'):
        abort(400)  # Bad Request

    if shortcode not in ('2454'):
        abort(400)  # Bad Request

    incoming_id = log_incoming(**args)

    app.logger.info(
        "Incoming SMS from number:%s saved with id:%s",
        args['msisdn'], incoming_id)

    return send_app_link(incoming_id=incoming_id, number=msisdn)

    app.logger.error('Unhandled SMS, incoming_id=%s', incoming_id)


@app.route('/')
def main():
    return 'Tekstmelding!'

if __name__ == '__main__':
    app.run()

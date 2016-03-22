#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from flask import Flask, request, g, abort, jsonify, render_template
import MySQLdb
import MySQLdb.cursors
import datetime
import logging
import logging.config

from utils import generate_activation_code, MyJSONEncoder
import sendega
import inside

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


def get_inside():
    if not hasattr(g, 'inside'):
        g.inside = inside.Inside(
            host=app.config['INSIDE_DB_HOST'],
            username=app.config['INSIDE_DB_USER'],
            password=app.config['INSIDE_DB_PASS'],
            db=app.config['INSIDE_DB_NAME'])
    return g.inside


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


def log_dlr(**kwargs):
    return query_db("""
        INSERT INTO dlr
            (msgid, extID, msisdn, status, statustext,
            registered, sent, delivered, errorcode,
            errormessage, operatorerrorcode)
        VALUES (
            %(msgid)s, %(extID)s, %(msisdn)s, %(status)s, %(statustext)s,
            %(registered)s, %(sent)s, %(delivered)s, %(errorcode)s,
            %(errormessage)s, %(operatorerrorcode)s)
    """, kwargs, lastrowid=True)


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


def notify_valid_membership(incoming_id=None, number=None, user=None):
    assert user

    name = get_inside().get_full_name(user)
    if user.get('expires_lifelong'):
        expires = 'verdens undergang'
    else:
        expires = str(user.get('expires'))

    content = "Hei %(name)s! Ditt medlemskap er gyldig til %(expires)s. Last ned app: %(app)s" % ({
        'name': name,
        'expires': expires,
        'app': 'http://snappo.com/app',
    })

    outgoing_id = send_sms(
        destination=number,
        content=content,
        incoming_id=incoming_id)

    app.logger.info("Sent SMS to number:%s with proof of membership", number)

    log_event(
        action='notify_valid_membership',
        incoming_id=incoming_id,
        outgoing_id=outgoing_id,
        user_id=user['id'])

    return 'OK'


def notify_pending_new_membership(incoming_id=None, number=None, activation_code=None):
    activation_url = 'https://s.neuf.no/sms/{number}/{activation_code}'.format(
        number=number,
        activation_code=activation_code,
    )
    content = 'Hei! Du har allerede betalt for et medlemskap. Aktiver det her: {}'.format(activation_url)

    outgoing_id = send_sms(
        destination=number,
        content=content,
        incoming_id=incoming_id)

    app.logger.info(
        "Resent activation code for number:%s", number)

    log_event(
        action='notify_pending_new_membership',
        incoming_id=incoming_id,
        outgoing_id=outgoing_id)

    return 'OK'


def notify_could_not_charge(incoming_id=None, dlr_id=None, number=None):
    app.logger.warning(
        "Attempt to charge number:%s as a response to incoming_id:%s failed",
        number, incoming_id)

    content = "Beklager, bestillingen kunne ikke gjennomføres. Spørsmål? medlem@studentersamfundet.no"

    outgoing_id = send_sms(
        destination=number,
        content=content,
        incoming_id=incoming_id)

    log_event(
        action='notify_could_not_charge',
        incoming_id=incoming_id,
        outgoing_id=outgoing_id,
        dlr_id=dlr_id)

    return 'OK'


def renew_membership(incoming_id=None, number=None, user=None):
    new_expire = datetime.date.today() + datetime.timedelta(days=365)

    content = "Hei %(name)s! Ditt medlemskap er nå gyldig ut %(new_expire)s. Spørsmål? %(email)s" % ({
        'name': get_inside().get_full_name(user),
        'new_expire': str(new_expire),
        'email': 'medlem@studentersamfundet.no'
    })

    # Log the event first, just in case the DLR is instant
    event_id = log_event(
        action='renew_membership',
        incoming_id=incoming_id,
        user_id=user['id'])

    outgoing_id = send_sms(
        destination=number,
        content=content,
        incoming_id=incoming_id,
        billing=True,
        price=app.config['MEMBERSHIP_PRICE_KR'] * 100,
    )

    update_event(event_id=event_id, outgoing_id=outgoing_id)

    app.logger.info(
        "Membership renewal requested by user_id:%s number:%s new_expire:%s",
        user['id'], number, new_expire)

    return 'OK'


def renew_membership_delivered(incoming_id=None, dlr_id=None, user_id=None):
    new_expire = datetime.date.today() + datetime.timedelta(days=365)
    get_inside().renew_user(user_id=user_id, new_expire=new_expire)

    app.logger.info(
        "Response to incoming_id:%s was delivered, user_id:%s renewed to %s",
        incoming_id, user_id, new_expire)

    log_event(
        action='renew_membership_delivered',
        incoming_id=incoming_id,
        dlr_id=dlr_id)

    return 'OK'


def new_membership(incoming_id=None, number=None):
    activation_code = generate_activation_code()

    content = "Velkommen som medlem! Hent ditt medlemskort i baren på Chateau Neuf."

    # Log the event first, just in case the DLR is instant
    event_id = log_event(
        action='new_membership',
        incoming_id=incoming_id,
        activation_code=activation_code)

    outgoing_id = send_sms(
        destination=number,
        content=content,
        incoming_id=incoming_id,
        billing=True,
        price=app.config['MEMBERSHIP_PRICE_KR'] * 100)

    update_event(event_id=event_id, outgoing_id=outgoing_id)

    app.logger.info(
        "New membership requested by number:%s, activation code sent", number)

    return 'OK'


def new_membership_delivered(incoming_id=None, dlr_id=None):
    app.logger.info(
        "Response to incoming_id:%s was delivered, new membership", incoming_id)

    log_event(
        action='new_membership_delivered',
        incoming_id=incoming_id,
        dlr_id=dlr_id)

    return 'OK'


def get_activation_code_purchase_date(number, activation_code):
    row = query_db("""
        SELECT event.timestamp FROM incoming, event
        WHERE incoming.msisdn = %s
        AND incoming.id = event.incoming_id
        AND event.action = 'new_membership'
        AND event.activation_code = %s""", [number, activation_code], one=True)
    return str(row.get('timestamp')) if row else None


def has_pending_new_membership(number):
    # WAT
    row = query_db("""
        SELECT event.activation_code FROM event
        WHERE event.incoming_id IN (
            SELECT event.incoming_id FROM incoming, event, event AS event2
            WHERE incoming.msisdn = %s
            AND incoming.id = event.incoming_id
            AND event.action = 'new_membership'
            AND event.timestamp > DATE_SUB(CURDATE(), INTERVAL 1 YEAR)
            AND event2.incoming_id = event.incoming_id
            AND event2.action = 'new_membership_delivered')
        AND activation_code IS NOT NULL""", [number], one=True)

    # What about card_number,phonenumber-tuples from kassa.neuf.no?
    # TODO: lookup phone number-bound-memberships from kassa, not from incoming sms-s
    # TODO: or should the place calling this function check an inside-table?
    return row.get('activation_code') if row else None


@app.route('/inside-code-purchase-date')
def inside_code_purchase_date():
    number = request.args.get('number')
    activation_code = request.args.get('activation_code')
    api_key = request.args.get('api_key')

    if api_key != app.config['INSIDE_API_KEY']:
        abort(403)  # Forbidden

    if None in (number, activation_code):
        return ''

    purchase_date = get_activation_code_purchase_date(number, activation_code)

    app.logger.info(
        'Inside checked purchase date for '
        'number:%s activation_code:%s purchase_date:%s',
        number, activation_code, purchase_date)

    return purchase_date or ''


@app.route('/kassa/pending-membership')
def kassa_pending_membership():
    """ Checks has_pending_new_membership on specified number and returns activation code and purchase date. """
    number = request.args.get('number')
    api_key = request.args.get('api_key')

    if api_key != app.config['INSIDE_API_KEY']:
        abort(403)  # Forbidden

    if number is None or len(number) == 0:
        return jsonify(**{'error': 'Missing or empty param number'})

    if number[0] == '+':
        number = number.replace('+', '')

    if not number.isdigit():
        return jsonify(**{'error': "Param number is not numerical '{}'".format(number)})

    activation_code = has_pending_new_membership(number)
    if activation_code is None:
        return jsonify(**{'result': None})

    result = {
        'number': number,
        'activation_code': activation_code,
        'purchase_date': get_activation_code_purchase_date(number, activation_code) if activation_code else None
    }
    return jsonify(**{'result': result})


@app.route('/kassa/new-membership-card', methods=['POST'])
def kassa_notify_new_card():
    """ Notify user Adds a pending membership to specified number """
    api_key = request.args.get('api_key')

    data = request.get_json()
    phone_number = data.get('phone_number')
    card_number = data.get('card_number')
    action = data.get('action')  # FIXME: not used

    if api_key != app.config['INSIDE_API_KEY']:
        abort(403)  # Forbidden

    if action is None or card_number is None:
        return jsonify(**{'error': 'Missing required param action or card_number'}), 400

    if phone_number is None or len(phone_number) == 0:
        return jsonify(**{'error': 'Missing or empty param phone_number'}), 400

    if phone_number[0] == '+':
        number = phone_number.replace('+', '')
    else:
        number = phone_number

    if not number.isdigit():
        return jsonify(**{'error': "Param number is not numerical '{}'".format(number)}), 400

    log_msg = "Kassa notify new card, number: {}, card_number: {}".format(number, card_number)
    app.logger.debug(log_msg)

    context = {
        'phone_number': phone_number,
        'activation_code': card_number,
        'action': action
    }
    content = render_template('notify_new_card.txt', **context)
    outgoing_id = send_sms(destination=number, content=content)

    log_event(action='new_membership_card', activation_code=card_number, outgoing_id=outgoing_id)

    return jsonify(**{'result': 'SMS sent OK', 'content': content, 'outgoing_id': outgoing_id})


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

    if shortcode not in ('2454',):
        abort(400)  # Bad Request

    incoming_id = log_incoming(**args)

    app.logger.info(
        "Incoming SMS from number:%s saved with id:%s",
        args['msisdn'], incoming_id)

    user = get_inside().get_user_by_phone(msisdn)

    if user:
        expired = get_inside().user_is_expired(user)

        if not expired:
            return notify_valid_membership(
                incoming_id=incoming_id, number=msisdn, user=user)
        elif expired:
            return renew_membership(
                incoming_id=incoming_id, number=msisdn, user=user)
    else:
        activation_code = has_pending_new_membership(msisdn)

        if activation_code:
            return notify_pending_new_membership(
                incoming_id=incoming_id, number=msisdn, activation_code=activation_code)
        else:
            return new_membership(
                incoming_id=incoming_id, number=msisdn)

    app.logger.error('Unhandled SMS, incoming_id=%s', incoming_id)


@app.route('/sendega-dlr', methods=['POST'])
def dlr():
    args = {'ip': request.headers.get('X-Real-IP') or request.remote_addr}

    for key in ('msgid', 'extID', 'msisdn', 'status', 'statustext',
                'registered', 'sent', 'delivered',
                'errorcode', 'errormessage', 'operatorerrorcode'):
        args[key] = request.form.get(key)

    app.logger.debug("Dlr, args: %s", args)

    dlr_id = log_dlr(**args)

    # We need to check what the original message was all about
    incoming_id = args['extID']

    success = (args['status'] == '4')
    if not success:
        return notify_could_not_charge(
            incoming_id=incoming_id, dlr_id=dlr_id, number=args['msisdn'])

    event = query_db("""
        SELECT * FROM event
        WHERE incoming_id=%s
        AND action IN ('new_membership', 'renew_membership')
        """, [incoming_id], one=True)

    if not event:
        app.logger.error('Got an unknown delivery report, dlr_id=%s', dlr_id)
        return 'what'

    action = event['action']

    if action == 'renew_membership':
        return renew_membership_delivered(
            incoming_id=incoming_id, dlr_id=dlr_id, user_id=event['user_id'])
    elif action == 'new_membership':
        return new_membership_delivered(
            incoming_id=incoming_id, dlr_id=dlr_id)

    app.logger.error('Unhandled DLR, dlr_id=%s', dlr_id)


@app.route('/stats/memberships/', methods=['GET'])
def stats_memberships():
    start_datetime = request.args.get('start', '2015-08-01')
    sale_events = query_db("""
        SELECT DATE_FORMAT(timestamp, '%%Y-%%m-%%d') as date,count(*) as sales FROM event
        WHERE action IN ('new_membership_delivered', 'renew_membership_delivered')
        AND timestamp > %s
        GROUP BY DATE_FORMAT(timestamp, '%%Y-%%m-%%d')
        ORDER BY timestamp""", [start_datetime])

    result = {'meta': {'num_results': len(sale_events)}, 'memberships': sale_events}
    headers = {'Access-Control-Allow-Origin': '*'}
    return jsonify(**result), 200, headers


@app.route('/stats/memberships/series', methods=['GET'])
def stats_memberships_stats():
    start_datetime = request.args.get('start', '2015-08-01')
    sale_events = query_db("""
        SELECT DATE_FORMAT(timestamp, '%%Y-%%m-%%d %%T') as date FROM event
        WHERE action IN ('new_membership_delivered', 'renew_membership_delivered')
        AND timestamp > %s
        ORDER BY timestamp""", [start_datetime])

    result = {
        'meta': {'num_results': len(sale_events)},
        'memberships': [x['date'] for x in sale_events]
    }
    headers = {'Access-Control-Allow-Origin': '*'}
    return jsonify(**result), 200, headers


@app.route('/')
def main():
    return 'Tekstmelding!'

if __name__ == '__main__':
    app.run()

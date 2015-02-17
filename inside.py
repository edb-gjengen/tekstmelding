#!/usr/bin/env python
# -*- coding: utf-8 -*-

import MySQLdb
import MySQLdb.cursors
import datetime


class Inside(object):
    """Inside."""

    def __init__(self, host, username, password, db):
        self.conn = MySQLdb.connect(
            host=host,
            user=username,
            passwd=password,
            db=db,
            cursorclass=MySQLdb.cursors.DictCursor,
            charset='utf8')

    def query_db(self, query, args=(), one=False, lastrowid=False):
        """Queries the database."""
        assert not (one and lastrowid)

        cur = self.conn.cursor()
        cur.execute(query, args)

        if lastrowid:
            ret = cur.lastrowid
        else:
            rv = cur.fetchall()
            ret = (rv[0] if rv else None) if one else rv

        self.conn.commit()
        cur.close()
        return ret

    def get_user_by_phone(self, number):
        user = self.query_db("""
            SELECT user.*,
                   (CASE WHEN (user.expires IS NULL) THEN 1 ELSE 0 END) AS expires_lifelong
            FROM din_user user, din_userphonenumber phone
            WHERE (phone.number = %s OR phone.number = %s) AND
                  user.id = phone.user_id
        """, ['+' + number, number], one=True)
        return user

    def user_is_expired(self, user):
        # A friendly reminder about how the 'expires' column works:
        #   NULL means the membership should never expire
        #   0000-00-00 is the default and means the user has never had a membership
        #   YYYY-MM-DD is the day the membership will or has expired
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

    def renew_user(self, user_id, new_expire):
        self.query_db(
            "UPDATE din_user SET expires = %(expires)s WHERE id = %(id)s", {
                'expires': str(new_expire),
                'id': user_id
            })

        self.query_db("""
            INSERT INTO din_userupdate
                (date, user_id_updated, comment, user_id_updated_by)
            VALUES
                (%(date)s, %(user_id_updated)s, %(comment)s, %(user_id_updated_by)s)
        """, {
            'date': str(datetime.datetime.now()),
            'user_id_updated': user_id,
            'comment': "Medlemskap fornyet med SMS.",
            'user_id_updated_by': user_id,
        })

    def get_full_name(self, user):
        full_name = "%s %s" % (
            user.get('firstname', '').strip(),
            user.get('lastname', '').strip()
        )
        return full_name[:50].strip()

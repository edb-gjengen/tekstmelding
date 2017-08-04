#!/usr/bin/env python
# -*- coding: utf-8 -*-

import requests


class Dusken(object):
    """ Dusken API """

    url = None
    api_key = None

    def __init__(self, url, api_key):
        self.url = url
        self.api_key = api_key

    @property
    def dusken_auth(self):
        return {'Authorization': 'Token {}'.format(self.api_key)}

    def get_user_by_phone(self, phone_number):
        url = '{}users/'.format(self.url)
        payload = {'phone_number': phone_number}
        users = requests.get(url, params=payload, headers=self.dusken_auth).json()
        if users.get('count') == 1:
            return users.get('results')[0]
        return None

    def get_full_name(self, user):
        full_name = '{} {}'.format(
            user.get('first_name', '').strip(),
            user.get('last_name', '').strip()
        )
        return full_name[:50].strip()

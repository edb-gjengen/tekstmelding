#!/usr/bin/env python
# -*- coding: utf-8 -*-

import suds


class Sendega(object):
    """Sendega."""

    def __init__(self, wsdl, username, password,
                 sender_bulk, sender_billing, dlr_url,
                 service_port='ContentSoap'):
        self.wsdl = wsdl
        self.username = username
        self.password = password
        self.sender_bulk = sender_bulk
        self.sender_billing = sender_billing
        self.dlr_url = dlr_url
        self.service_port = service_port

        self.client = suds.client.Client(wsdl)
        self.client.set_options(port=self.service_port)

    def create_sms(self, destination, content, billing=False,
                   price=0, reference=None):
        if isinstance(destination, (list, tuple, set)):
            assert len(destination) <= 100, "Max 100 destinations"
            destination = ','.join(destination)

        args = {
            'username': self.username,
            'password': self.password,
            'sender': self.sender_billing if billing else self.sender_bulk,
            'destination': destination,  # "4712345678", may be comma separated
            'pricegroup': price,  # 100 = 1 kr
            'contentTypeID': 5 if billing else 1,  # 1 = bulk, 5 = premium GAS
            'contentHeader': "",  # empty string for other content types
            'content': content,  # gets split automatically if length > 160
            'dlrUrl': self.dlr_url if billing else "",
            'ageLimit': 0,  # end-user age limit for premium or adult services
            'extID': str(reference) if reference else "",  # local unique ID, returned in DLR
            'sendDate': "",  # delayed delivery, YYYY-MM-DD HH:MM:SS
            'refID': "",  # used when sending premium SMS to some countries
            'priority': 0,  # 0 = normal priority
            'gwID': 0,  # specific gateway
            'pid': 0,  # protocol id
            'dcs': 0,  # data coding scheme
        }

        return args

    def send(self, **kwargs):
        result = self.client.service.Send(kwargs)

        return dict(result)

# -*- coding: utf-8 -*-

import json
import MySQLdb
import logging
import eventlet
from eventlet.green import urllib2

LOG = logging.getLogger()

from settings import mysql_addr, mysql_port, mysql_user, \
        mysql_pwd, mysql_db, agent_api_port

class AgentView(object):

    def __init__(self):
        self.db = MySQLdb.connect(host=mysql_addr, port=mysql_port, user=mysql_user, \
                passwd=mysql_pwd, db=mysql_db)
        self._agent_list = {}
        self._pool = eventlet.GreenPool(size=256)

        self._initial_agent_list()

    def _initial_agent_list(self):
        cur = self.db.cursor()
        sql = "select id, addr from agent_manager where status=1"
        cur.execute(sql)
        for row in cur.fetchall():
            self._agent_list[row[0]] = row[1]
        LOG.debug("Agent list: %s", self._agent_list)

    def register_agent(self, info):
        """
        :param info: {'id':, 'addr':}
        """
        if self._agent_list.has_key(info.id):
            return {
                'success': False,
                'reason': "Agent %s already existed." % info.id
            }

        cur = self.db.cursor()
        re = cur.execute("select id from agent_manager where id='%s'" % info.id)
        if re == 0:
            sql = "insert into agent_manager(id, addr, status) values ('%s', '%s', 1)" \
                    % (info.id, info.addr)
            cur.execute(sql)
        else:
            sql = "update agent_manager set addr='%s', status=%d where id='%s'" \
                    % (info.addr, 1, info.id)
            cur.execute(sql)
        self.db.commit()
        self._agent_list[info.id] = info.addr
        return {'success': True}

    def unregister_agent(self, agent_id):
        if not self._agent_list.has_key(agent_id):
            return {
                'success': False,
                'reason': 'Agent %s was not registered.' % agent_id
            }

        cur = self.db.cursor()
        re = cur.execute("delete from agent_manager where id='%s'" % agent_id)
        self.db.commit()
        del self._agent_list[agent_id]
        return {'success': True}

    def ping_agents(self):

        def __ping(args):
            try:
                re = urllib2.urlopen(args[1]).read()
                return {
                    'success': True,
                    'id': args[0],
                    'info': re
                }
            except Exception, e:
                LOG.error(e)
                return {
                    'success': False,
                    'id': args[0],
                    'info': e
                }
        
        addrs = [(k, "http://%s:%s/api/ping" % (v, agent_api_port)) \
                for k, v in self._agent_list.items()]
        cur = self.db.cursor()
        for ret in self._pool.imap(__ping, addrs):
            LOG.debug(ret)
            if not ret['success']:
                self.unregister_agent(ret['id'])

            info = json.loads(ret['info'])
            cur.execute("update agent_manager set volume=%f where id='%s'" \
                    % (info['volume'], ret['id']))
        self.db.commit()
   
agent_view = AgentView()


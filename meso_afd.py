#!/usr/bin/env python
# Process special AFD for BMX

import sys, re
import traceback
import StringIO
from settings import *
from pyIEM import nws_text
from pyxmpp.jid import JID
from pyxmpp.jabber.simple import send_message

errors = StringIO.StringIO()


raw = sys.stdin.read()

if (HAVE_POSTGIS):
    try:
        import pg
        postgisdb = pg.connect(dbname=postgis_dbname, host=postgis_host,
          port=postgis_port, opt=postgis_opt, tty=postgis_tty,
          user=postgis_user, passwd=postgis_passwd)
    except:
        errors.write("\nWarn: Can't connect to Postgis. Disabling Postgis.\n")
        traceback.print_exc(errors)
        HAVE_POSTGIS = 0

def calldb(sql):
    if (not HAVE_POSTGIS):
        return

    try:
        postgisdb.query(sql)
    except:
        errors.write("\n-----------\nSQL: %s\n" % (sql,) )
        traceback.print_exc(file=errors)
        errors.write("\n-----------\n")

def querydb(sql):
    if (not HAVE_POSTGIS):
        return []

    try:
        return postgisdb.query(sql).dictresult()
    except:
        errors.write("\n-----------\nSQL: %s\n" % (sql,) )
        traceback.print_exc(file=errors)
        errors.write("\n-----------\n")

    return []

def sendJabberMessage(jabberTxt):
    jid=JID(jabber_from_jid)
    recpt=JID(jabber_to_jid)
    send_message(jid, jabber_passwd, recpt, jabberTxt, 'Ba')

def process(raw):
    afos = sys.argv[1]
    pil = afos[:3]
    wfo = afos[3:]
    raw = raw.replace("'", "\\'")

    tokens = re.findall("\.UPDATE\.\.\.MESOSCALE UPDATE", raw)
    if (len(tokens) == 0):
        return

    sql = "INSERT into text_products(product) values ('%s')" % (raw,)
    calldb(sql)
    sql = "select last_value from text_products_id_seq"
    rs = querydb(sql)
    id = rs[0]['last_value']
    mess = "%s: %s issues Mesoscale %s http://mesonet.agron.iastate.edu/p.php?id=%s" % \
        (wfo, wfo, pil, id)
    sendJabberMessage(mess)
                
    errors.seek(0)
    print errors.read()
if __name__ == "__main__":
    process(raw)


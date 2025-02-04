""" LSR product ingestor """
# Stdlib
import pickle
import os
import datetime

# 3rd Party
import pytz
from twisted.internet import reactor
from pyiem import reference
from pyiem.nws.products.lsr import parser as lsrparser
from pyiem.util import LOG

# Local
from pywwa import common
from pywwa.ldm import bridge
from pywwa.database import get_database

# Cheap datastore for LSRs to avoid Dups!
LSRDB = {}


def loaddb():
    """load memory"""
    if os.path.isfile("lsrdb.p"):
        mydict = pickle.load(open("lsrdb.p", "rb"))
        for key in mydict:
            LSRDB[key] = mydict[key]


def cleandb():
    """To keep LSRDB from growing too big, we clean it out
    Lets hold 7 days of data!
    """
    utc = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
    thres = utc - datetime.timedelta(hours=24 * 7)
    init_size = len(LSRDB)
    # loop safety here
    for key in list(LSRDB):
        if LSRDB[key] < thres:
            LSRDB.pop(key)

    fin_size = len(LSRDB)
    LOG.info("cleandb() init_size: %s final_size: %s", init_size, fin_size)
    # Non blocking hackery
    reactor.callInThread(pickledb)

    # Call Again in 30 minutes
    reactor.callLater(60 * 30, cleandb)


def pickledb():
    """Dump our database to a flat file"""
    pickle.dump(LSRDB, open("lsrdb.p", "wb"))


def real_processor(txn, text):
    """Lets actually process!"""
    prod = lsrparser(text)

    for lsr in prod.lsrs:
        if lsr.typetext.upper() not in reference.lsr_events:
            errmsg = "Unknown LSR typecode '%s'" % (lsr.typetext,)
            common.email_error(errmsg, text)
        uniquekey = hash(lsr.text)
        if uniquekey in LSRDB:
            prod.duplicates += 1
            lsr.duplicate = True
            continue
        LSRDB[uniquekey] = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
        if common.dbwrite_enabled():
            lsr.sql(txn)

    j = prod.get_jabbers(common.SETTINGS.get("pywwa_lsr_url", "pywwa_lsr_url"))
    for i, (p, h, x) in enumerate(j):
        # delay some to perhaps stop triggering SPAM lock outs at twitter
        reactor.callLater(i, common.send_message, p, h, x)

    if prod.warnings:
        common.email_error("\n\n".join(prod.warnings), text)
    elif not prod.lsrs:
        raise Exception("No LSRs parsed!", text)


def main():
    """Go Main Go."""
    common.main()
    reactor.callLater(0, loaddb)
    bridge(real_processor, dbpool=get_database("postgis"))
    reactor.callLater(20, cleandb)
    reactor.run()


if __name__ == "__main__":
    main()

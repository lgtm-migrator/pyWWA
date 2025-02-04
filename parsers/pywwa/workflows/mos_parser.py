""" MOS Data Ingestor, why not? """

# 3rd Party
from twisted.internet import reactor
from pyiem.nws.products.mos import parser

# Local
from pywwa import common
from pywwa.ldm import bridge
from pywwa.database import get_database

DBPOOL = get_database("mos")
MEMORY = {"ingested": 0}


def process_data(data):
    """
    Actual ingestor
    """
    try:
        real_process(data)
    except Exception as myexp:
        common.email_error(myexp, data)


def got_data(res):
    """Callback from the database save"""
    MEMORY["ingested"] += res


def real_process(text):
    """The real processor of the raw data, fun!"""
    prod = parser(text, utcnow=common.utcnow())
    if not common.dbwrite_enabled():
        return
    if prod.warnings:
        common.email_error("\n".join(prod.warnings), text)
    df = DBPOOL.runInteraction(prod.sql)
    df.addCallback(got_data)
    df.addErrback(common.email_error, text)


def main():
    """Go Main Go."""
    common.main(with_jabber=False)
    bridge(process_data)
    reactor.run()


if __name__ == "__main__":
    main()

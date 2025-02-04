""" Generic NWS Product Parser """
# stdlib
from datetime import timedelta

# 3rd Party
from twisted.internet import reactor
from shapely.geometry import MultiPolygon
from pyiem.util import LOG
from pyiem.nws.ugc import UGCProvider
from pyiem.nws.product import TextProduct
from pyiem.nws.products import parser as productparser

# Local
from pywwa import common
from pywwa.ldm import bridge
from pywwa.database import load_nwsli, get_database

UGC_DICT = UGCProvider()
NWSLI_DICT = {}
PGCONN = get_database("postgis")


def error_wrapper(exp, buf):
    """Don't whine about known invalid products"""
    if buf.find("HWOBYZ") > -1:
        LOG.info("Skipping Error for HWOBYZ")
    else:
        common.email_error(exp, buf)


def process_data(data):
    """Process the product"""
    defer = PGCONN.runInteraction(really_process_data, data)
    defer.addErrback(error_wrapper, data)
    defer.addErrback(LOG.error)


def really_process_data(txn, buf) -> TextProduct:
    """Actually do some processing"""

    # Create our TextProduct instance
    prod = productparser(
        buf,
        utcnow=common.utcnow(),
        ugc_provider=UGC_DICT,
        nwsli_provider=NWSLI_DICT,
    )

    # Do the Jabber work necessary after the database stuff has completed
    for (plain, html, xtra) in prod.get_jabbers(
        common.SETTINGS.get("pywwa_product_url", "pywwa_product_url")
    ):
        if xtra.get("channels", "") == "":
            common.email_error("xtra[channels] is empty!", buf)
        common.send_message(plain, html, xtra)

    if not common.dbwrite_enabled():
        return None
    # Insert into database only if there is a polygon!
    if not prod.segments or prod.segments[0].sbw is None:
        return None

    expire = prod.segments[0].ugcexpire
    if expire is None:
        prod.warnings.append("ugcexpire is none, defaulting to 90 minutes.")
        expire = prod.valid + timedelta(minutes=90)
    product_id = prod.get_product_id()
    giswkt = f"SRID=4326;{MultiPolygon([prod.segments[0].sbw]).wkt}"
    sql = (
        "INSERT into text_products(product_id, geom, issue, expire, pil) "
        "values (%s,%s,%s,%s,%s)"
    )
    myargs = (
        product_id,
        giswkt,
        prod.valid,
        expire,
        prod.afos,
    )
    txn.execute(sql, myargs)
    if prod.warnings:
        common.email_error("\n".join(prod.warnings), buf)
    return prod


def main():
    """Go Main Go."""
    common.main()
    load_nwsli(NWSLI_DICT)
    bridge(process_data)

    reactor.run()


if __name__ == "__main__":
    main()

# Copyright (c) 2005-2008 Iowa State University
# http://mesonet.agron.iastate.edu/ -- mailto:akrherz@iastate.edu
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
""" SHEF product ingestor """

# Setup Standard Logging we use
from twisted.python import log
log.startLogging(open('logs/shef_parser.log', 'a'))
log.FileLogObserver.timeFormat = "%Y/%m/%d %H:%M:%S %Z"

# System Imports
import os, smtplib
from email.mime.text import MIMEText

o = open("shef_parser.pid",'w')
o.write("%s" % ( os.getpid(),) )
o.close()

# Stuff I wrote
from pyIEM import iemAccessOb, mesonet, iemdb
from support import ldmbridge, TextProduct
import secret

# Third Party Stuff
from twisted.internet import reactor, protocol
from twisted.enterprise import adbapi
import mx.DateTime


# Setup Database Links
ACCESSDB = adbapi.ConnectionPool("psycopg2", database='iem', host=secret.dbhost)
HADSDB = adbapi.ConnectionPool("psycopg2", database='hads', host=secret.dbhost)
i = iemdb.iemdb(secret.dbhost)
IEMACCESS = i['iem']

# Necessary for the shefit program to run A-OK
os.chdir("/home/ldm/pyWWA/shef_workspace")

MULTIPLIER = {
  "US" : 0.87,  # Convert MPH to KNT
  "UG": 0.87,
  "UP": 0.87,
  "UR": 10,
}

# Ugly hack on how we map SHEFIT vars to iemaccess variables
MAPPING = {
  "HGIRZ": "rstage",
  "HGIRG": "rstage",
  "HGIRGZ": "rstage",
  "HG": "rstage",

  "HPIRGZ": "rstage",
  "HPIRPZ": "rstage",

  "PPHRGZ": "phour",
  "PPHRPZ": "phour",
  "PPHRG": "phour", 
  "PPH": "phour",

  "TD": "dwpf",
  "TDIRGZ": "dwpf",
  "TDIRZZ": "dwpf",
 
  "TAIRG": "tmpf",
  "TAIRGZ": "tmpf",
  "TAIRZZ": "tmpf", 
  "TA": "tmpf",

  "TAIRZNZ": "min_tmpf", 
  "TAIRGN": "min_tmpf", 
  "TN": "min_tmpf",

  "TAIRZXZ": "max_tmpf",
  "TAIRGX": "max_tmpf",
  "TX": "max_tmpf",

  "PPDRZZ": "pday",
  "PPD": "pday",
  "PP": "pday",

  "RWIRGZ": "srad",

  "SD": "snowd", 
  "SDIRZZ": "snowd", 
  "SDIRGZ": "snowd", 
 
  "XR": "relh",
  "XRIRGZ": "relh",

  "PA": "pres", 
  "PAIRGZ": "pres", 

  "SW": "snoww",
  "SWIRZZ": "snoww",

  "USIRG": "sknt",
  "USIRGZ": "sknt",
  "US": "sknt",
  "USIRZZ": "sknt",
 
  "SF": "snow",
  "SFDRZZ": "snow",

  "UD": "drct", 
  "UDIRG": "drct",
  "UDIRGZ": "drct",
  "UDIRZZ": "drct",

  "UG": "gust", 
  "UGIRZZ": "gust",

  "UPHRGZ": "max_sknt",
  "UPIRG": "max_sknt",
  "UPVRG": "max_sknt",
  "UPVRGZ": "max_sknt",
  "UPJRGZ": "max_sknt",
  "UPIRZZ": "max_sknt",

  "URIRZZ": "max_drct",
  "URHRGZ": "max_drct",
}

COOPSTATES = ['IA', 'ND', 'SD', 'NE', 'KS', 'MO',
            'MN', 'WI', 'IL', 'IN', 'OH', 'MI']
COOPVARS = ['TAIRGX', 'TAIRGN', 'TAIRZNZ', 'TAIRZXZ', 'PPDRZZ']
EMAILS = 10

class MyIEMOB(iemAccessOb.iemAccessOb):
    """
    Override the iemAccessOb class with my own query engine, so that we 
    can capture errors for now!
    """

    def execQuery(self, sql, dbase, dbpool):
        """
        Execute queries with an error callback!
        """
        dbpool.runOperation( sql ).addErrback( email_error, sql)

class SHEFIT(protocol.ProcessProtocol):
    """
    My process protocol for dealing with the SHEFIT program from the NWS
    """

    def __init__(self, tp):
        """
        Constructor
        """
        self.tp = tp
        self.data = ""

    def connectionMade(self):
        """
        Fired when the program starts up and wants stdin
        """
        #print "sending %d bytes!" % len(self.shefdata)
        #print "SENDING", self.shefdata
        self.transport.write( self.tp.raw )
        self.transport.closeStdin()

    def outReceived(self, data):
        """
        Save the stdout we get from the program for later processing
        """
        #print "GOT", data
        self.data = self.data + data

    def errReceived(self, data):
        """
        In case something comes to stderr 
        """
        print "errReceived! with %d bytes!" % len(data)
        print data

#    def processEnded(self, status):
#        print "debug: type(status): %s" % type(status.value)
#        print "error: exitCode: %s" % status.value.exitCode


    def outConnectionLost(self):
        """
        Once the program is done, we need to do something with the data
        """
        if self.data == "":
            rejects = open("empty.shef", 'a')
            rejects.write( self.tp.raw +"\003")
            rejects.close()
            return
        try:
            really_process(self.tp, self.data)
        except Exception,myexp:
            email_error(myexp, self.tp.raw)

def email_error(message, product_text, tp=None):
    """
    Generic something to send email error messages 
    """
    global EMAILS
    log.msg( message )
    EMAILS -= 1
    if (EMAILS < 0):
        return
    if tp is not None:
        product_text = tp.raw
    msg = MIMEText("Exception:\n%s\n\nRaw Product:\n%s\n%s" % ( 
                 message, tp or "", product_text))
    msg['subject'] = 'shef_parser.py Traceback'
    msg['From'] = secret.parser_user
    msg['To'] = 'akrherz@iastate.edu'
    smtp = smtplib.SMTP()
    smtp.connect()
    smtp.sendmail(msg['From'], msg['To'], msg.as_string())
    smtp.close()

def clnstr(buf):
    buf = buf.replace("\015\015\012", "\n")
    buf = buf.replace("\003", "")
    return buf.replace("\001", "")

class MyProductIngestor(ldmbridge.LDMProductReceiver):

    def connectionLost(self, reason):
        print 'connectionLost', reason
        reactor.callLater(5, self.shutdown)

    def shutdown(self):
        reactor.callWhenRunning(reactor.stop)

    def process_data(self, buf):
        """
        I am called from the ldmbridge when data is ahoy
        """
        tp = TextProduct.TextProduct( clnstr(buf) )
        shef = SHEFIT( tp )
        reactor.spawnProcess(shef, "shefit", ["shefit"], {})

def i_want_site(sid):
    """ Return bool if I want to actually process this site """
    if sid in ['3SE','3OI']:
        return True
    if (len(sid) != 5):
        return False
    if (not mesonet.nwsli2state.has_key(sid[-2:])):
        return False

    # We want all state's COOP data now :)
    #state = mesonet.nwsli2state[ sid[-2:]]
    #if (not state in COOPSTATES):
    #    return False

    return True

def really_process(tp, data):
    """
    This processes the output we get from the SHEFIT program
    """
    # Now we loop over the data we got :)
    mydata = {}
    for line in data.split("\n"):
        # Skip blank output lines
        if line.strip() == "":
            continue
        tokens = line.split()
        if len(tokens) < 7:
            print "NO ENOUGH TOKENS", line
            continue
        sid = tokens[0]
        if not i_want_site(sid):
            continue
        if (not mydata.has_key(sid)):
            mydata[sid] = {}
        dstr = "%s %s" % (tokens[1], tokens[2])
        tstamp = mx.DateTime.strptime(dstr, "%Y-%m-%d %H:%M:%S")
        if (not mydata[sid].has_key(tstamp)):
            mydata[sid][tstamp] = {}

        varname = tokens[5]
        value = float(tokens[6])
        mydata[sid][tstamp][varname] = value

    # Now we process each station we found in the report! :)
    for sid in mydata.keys():
        times = mydata[sid].keys()
        times.sort()
        for tstamp in times:
            process_site(tp, sid, tstamp, mydata[sid][tstamp])


def process_site(tp, sid, ts, data):
    """ 
    I process a dictionary of data for a particular site
    """
    isCOOP = 0
    if sid in ['3SE','3OI']:
        state = "IA"
    else:
        state = mesonet.nwsli2state[ sid[-2:]]
    #print sid, ts, mydata[sid][ts].keys()
    # Loop thru vars to see if we have a COOP site?
    for var in data.keys():
        if (var in COOPVARS):
            isCOOP = 1
        if (not MAPPING.has_key(var)):
            print "Couldn't map var: %s for SID: %s" % (var, sid)
            MAPPING[var] = ""
        if (not MULTIPLIER.has_key(var[:2])):
            MULTIPLIER[var[:2]] = 1.0
        HADSDB.runOperation("""INSERT into raw%s 
            (station, valid, key, value) 
            VALUES('%s','%s+00', '%s', '%s')""" % (ts.strftime("%Y_%m"), sid, 
            ts.strftime("%Y-%m-%d %H:%M"), var, 
            data[var])).addErrback(email_error, data, tp)

    #print sid, state, isCOOP
    # Deterime if we want to waste the DB's time
    # If COOP in MW, process it
    if (isCOOP):
        print "COOP? %s %s %s" %  (sid, tp.get_product_id(), data.keys())
        network = "%s_COOP" % (state,)
    # We are left with DCPs in Iowa
    elif (state == "IA"):
        network = "DCP"
    # Everybody else can go away :)
    else:
        return

    # Lets do this, finally.
    #print "ACTUALLY PROCESSED", sid, network
    iemob = MyIEMOB(sid, network)
    iemob.setObTimeGMT(ts)
    iemob.data['year'] = ts.year
    if not iemob.load_and_compare(IEMACCESS):
        #print 'Unknown StationID %s %s' %  (sid,  tp.get_product_id() )
        HADSDB.runOperation("""
            INSERT into unknown(nwsli, product) values ('%s', '%s')
        """ % (sid, tp.get_product_id() ))

    for var in data.keys():
        myval = data[var] * MULTIPLIER[var[:2]]
        iemob.data[ MAPPING[var] ] = myval
    iemob.updateDatabaseSummaryTemps(None, ACCESSDB)
    iemob.updateDatabase(None, ACCESSDB)

    del iemob

#
fact = ldmbridge.LDMProductFactory( MyProductIngestor() )
reactor.run()

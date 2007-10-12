############################################################################
##
## Copyright (C) 2006-2007 University of Utah. All rights reserved.
##
## This file is part of VisTrails.
##
## This file may be used under the terms of the GNU General Public
## License version 2.0 as published by the Free Software Foundation
## and appearing in the file LICENSE.GPL included in the packaging of
## this file.  Please review the following to ensure GNU General Public
## Licensing requirements will be met:
## http://www.opensource.org/licenses/gpl-license.php
##
## If you are unsure which license is appropriate for your use (for
## instance, you are interested in developing a commercial derivative
## of VisTrails), please contact us at vistrails@sci.utah.edu.
##
## This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
## WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
##
############################################################################

import os.path
import core.configuration
import core.system
from db.services import io
import urllib
from db import VistrailsDBException

class BaseLocator(object):

    def load(self):
        pass # returns a vistrail

    def save(self, vistrail):
        pass # saves a vistrail in the given place

    def save_as(self, vistrail):
        return self.save(vistrail) # calls save by default

    def is_valid(self):
        pass # Returns true if locator refers to a valid vistrail

    def save_temporary(self, vistrail):
        pass # Saves a temporary file (useful for making crashes less horrible)

    def clean_temporaries(self):
        pass # Cleans up temporary files

    def has_temporaries(self):
        pass # True if temporaries are present

    def serialize(self, dom, element):
        pass #Serializes this locator to XML

    @staticmethod
    def parse(element):
        pass #Parse an XML object representing a locator and returns a Locator
    
    def _get_name(self):
        pass # Returns a name that will be displayed for the vistrail
    name = property(_get_name)

    ###########################################################################
    # Operators

    def __eq__(self, other):
        pass # Implement equality

    def __ne__(self, other):
        pass # Implement nonequality

class XMLFileLocator(BaseLocator):
    def __init__(self, filename):
        self._name = filename
        config = core.configuration.get_vistrails_configuration()
        if config:
            self._dot_vistrails = config.dotVistrails
        else:
            self._dot_vistrails = core.system.default_dot_vistrails()

    def load(self):
        fname = self._find_latest_temporary()
        if fname:
            vistrail = io.open_vistrail_from_xml(fname)
        else:
            vistrail = io.open_vistrail_from_xml(self._name)
        vistrail.locator = self
        return vistrail

    def save(self, vistrail, do_copy=True):
        vistrail = io.save_vistrail_to_xml(vistrail, self._name)
        vistrail.locator = self
        # Only remove the temporaries if save succeeded!
        self.clean_temporaries()
        return vistrail

    def save_temporary(self, vistrail):
        fname = self._find_latest_temporary()
        new_temp_fname = self._next_temporary(fname)
        io.save_vistrail_to_xml(vistrail, new_temp_fname)

    def is_valid(self):
        return os.path.isfile(self._name)

    def _get_name(self):
        return self._name
    name = property(_get_name)

    def encode_name(self, filename):
        """encode_name(filename) -> str
        Encodes a file path using urllib.quoteplus

        """
        name = urllib.quote_plus(filename) + '_tmp_'
        return os.path.join(self._dot_vistrails, name)

    def serialize(self, dom, element):
        """serialize(dom, element) -> None
        Convert this object to an XML representation.

        """
        locator = dom.createElement('locator')
        locator.setAttribute('type', 'file')
        node = dom.createElement('name')
        filename = dom.createTextNode(str(self._name))
        node.appendChild(filename)
        locator.appendChild(node)
        element.appendChild(locator)

    @staticmethod
    def parse(element):
        """ parse(element) -> XMLFileLocator or None
        Parse an XML object representing a locator and returns a
        XMLFileLocator object.

        """
        if str(element.getAttribute('type')) == 'file':
            for n in element.childNodes:
                if n.localName == "name":
                    filename = str(n.firstChild.nodeValue).strip(" \n\t")
                    return XMLFileLocator(filename)
            return None
        else:
            return None

    def __str__(self):
        return '<%s vistrail_name=" %s/>' % (self.__class__.__name__, self._name)
    
    ##########################################################################

    def _iter_temporaries(self, f):
        """_iter_temporaries(f): calls f with each temporary file name, in
        sequence.

        """
        latest = None
        current = 0
        while True:
            fname = self.encode_name(self._name) + str(current)
            if os.path.isfile(fname):
                f(fname)
                current += 1
            else:
                break

    def clean_temporaries(self):
        """_remove_temporaries() -> None

        Erases all temporary files.

        """
        def remove_it(fname):
            os.unlink(fname)
        self._iter_temporaries(remove_it)

    def has_temporaries(self):
        return self._find_latest_temporary() is not None

    def _find_latest_temporary(self):
        """_find_latest_temporary(): String or None.

        Returns the latest temporary file saved, if it exists. Returns
        None otherwise.
        
        """
        latest = [None]
        def set_it(fname):
            latest[0] = fname
        self._iter_temporaries(set_it)
        return latest[0]
        
    def _next_temporary(self, temporary):
        """_find_latest_temporary(string or None): String

        Returns the next suitable temporary file given the current
        latest one.

        """
        if temporary == None:
            return self.encode_name(self._name) + '0'
        else:
            split = temporary.rfind('_')+1
            base = temporary[:split]
            number = int(temporary[split:])
            return base + str(number+1)

    ###########################################################################
    # Operators

    def __eq__(self, other):
        if type(other) != XMLFileLocator:
            return False
        return self._name == other._name

    def __ne__(self, other):
        return not self.__eq__(other)

class ZIPFileLocator(XMLFileLocator):
    """Files are compressed in zip format. The temporaries are
    still in xml"""
    def __init__(self, filename):
        XMLFileLocator.__init__(self, filename)

    def load(self):
        fname = self._find_latest_temporary()
        if fname:
            vistrail = io.open_vistrail_from_xml(fname)
        else:
            vistrail = io.open_vistrail_from_zip_xml(self._name)
        vistrail.locator = self
        return vistrail

    def save(self, vistrail, do_copy=True):
        vistrail = io.save_vistrail_to_zip_xml(vistrail, self._name)
        vistrail.locator = self
        # Only remove the temporaries if save succeeded!
        self.clean_temporaries()
        return vistrail

    ###########################################################################
    # Operators

    def __eq__(self, other):
        if type(other) != ZIPFileLocator:
            return False
        return self._name == other._name

    def __ne__(self, other):
        return not self.__eq__(other)

    @staticmethod
    def parse(element):
        """ parse(element) -> ZIPFileLocator or None
        Parse an XML object representing a locator and returns a
        ZIPFileLocator object.

        """
        if str(element.getAttribute('type')) == 'file':
            for n in element.childNodes:
                if n.localName == "name":
                    filename = str(n.firstChild.nodeValue).strip(" \n\t")
                    return ZIPFileLocator(filename)
            return None
        else:
            return None

class DBLocator(BaseLocator):
    
    connections = {}

    def __init__(self, host, port, database, user, passwd, name=None,
                 vistrail_id=None, connection_id=None):
        self._host = host
        self._port = port
        self._db = database
        self._user = user
        self._passwd = passwd
        self._vt_name = name
        self._vt_id = vistrail_id
        self._conn_id = connection_id

    def _get_host(self):
        return self._host
    host = property(_get_host)

    def _get_port(self):
        return self._port
    port = property(_get_port)

    def _get_vistrail_id(self):
        return self._vt_id
    vistrail_id = property(_get_vistrail_id)

    def _get_connection_id(self):
        return self._conn_id
    connection_id = property(_get_connection_id)
    
    def _get_name(self):
        return self._host + ':' + str(self._port) + ':' + self._db + ':' + \
            self._vt_name
    name = property(_get_name)

    def is_valid(self):
        if self._conn_id is not None \
                and DBLocator.connections.has_key(self._conn_id):
            return True
        else:
            config = {'host': str(self._host),
                      'port': int(self._port),
                      'db': str(self._db),
                      'user': str(self._user),
                      'passwd': str(self._passwd)}
            try:
                io.test_db_connection(config)
            except VistrailsDBException, e:
                return False
            return True
        
    def get_connection(self):
        if self._conn_id is not None \
                and DBLocator.connections.has_key(self._conn_id):
            connection = DBLocator.connections[self._conn_id]
        else:
            config = {'host': self._host,
                      'port': self._port,
                      'db': self._db,
                      'user': self._user,
                      'passwd': self._passwd}
            connection = io.open_db_connection(config)
            if self._conn_id is None:
                if len(DBLocator.connections.keys()) == 0:
                    self._conn_id = 1
                else:
                    self._conn_id = max(DBLocator.connections.keys()) + 1
            DBLocator.connections[self._conn_id] = connection
        return connection

    def load(self):
        connection = self.get_connection()
        vistrail = io.open_vistrail_from_db(connection, self.vistrail_id)
        self._vt_name = vistrail.db_name
        vistrail.locator = self
        return vistrail

    def save(self, vistrail, do_copy=False):
        connection = self.get_connection()
        vistrail.db_name = self._vt_name
        vistrail = io.save_vistrail_to_db(vistrail, connection, do_copy)
        self._vt_id = vistrail.db_id
        vistrail.locator = self
        return vistrail

    def serialize(self, dom, element):
        """serialize(dom, element) -> None
        Convert this object to an XML representation.

        """
        locator = dom.createElement('locator')
        locator.setAttribute('type', 'db')
        locator.setAttribute('host', str(self._host))
        locator.setAttribute('port', str(self._port))
        locator.setAttribute('db', str(self._db))
        locator.setAttribute('vt_id', str(self._vt_id))
        node = dom.createElement('name')
        filename = dom.createTextNode(str(self._vt_name))
        node.appendChild(filename)
        locator.appendChild(node)
        element.appendChild(locator)

    @staticmethod
    def parse(element):
        """ parse(element) -> DBFileLocator or None
        Parse an XML object representing a locator and returns a
        DBFileLocator object.

        """
        if str(element.getAttribute('type')) == 'db':
            host = str(element.getAttribute('host'))
            port = int(element.getAttribute('port'))
            database = str(element.getAttribute('db'))
            vt_id = str(element.getAttribute('vt_id'))
            user = None
            passwd = None
            for n in element.childNodes:
                if n.localName == "name":
                    name = str(n.firstChild.nodeValue).strip(" \n\t")
                    #print host, port, database, name, vt_id
                    return DBLocator(host, port, database,
                                     user, passwd, name, vt_id, None)
            return None
        else:
            return None

    def __str__(self):
        return '<DBLocator host="%s" port="%s" database="%s" vistrail_id="%s"\
vistrail_name="%s"/>' % ( self._host, self._port, self._db,
                          self._vt_id, self._vt_name)
    
    ###########################################################################
    # Operators

    def __eq__(self, other):
        if type(other) != type(self):
            return False
        return (self._host == other._host and
                self._port == other._port and
                self._db == other._db and
                self._user == other._user and
                self._vt_name == other._vt_name and
                self._vt_id == other._vt_id)

    def __ne__(self, other):
        return not self.__eq__(other)

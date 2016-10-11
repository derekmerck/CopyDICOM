import logging
import requests
from posixpath import join as urljoin
from urlparse import urlsplit

class OrthancSession(requests.Session):

    def __init__(self, address):

        super(OrthancSession, self).__init__()

        self.address = address
        p = urlsplit(self.address)
        self.scheme = p.scheme
        self.hostname = p.hostname
        self.port = p.port
        self.path = p.path
        self.auth = (p.username, p.password)

        self.logger = logging.getLogger("{0}:{1} API".format(self.hostname, self.port))
        self.logger.info('Created session wrapper for %s' % address)

    def get_url(self, *loc):
        return urljoin("{0}://{1}:{2}".format(self.scheme, self.hostname, self.port), self.path, *loc)

    def do_return(self, r):
        # Return dict if possible, but content otherwise (for image data)
        if r.status_code is not 200:
            self.logger.warn('Orthanc returned error %s', r.status_code)
            return r.content

        if r.headers.get('content-type') == 'application/json':
            try:
                ret = r.json()
            except ValueError:
                self.logger.warn('Orthanc returned malformed json')
                ret = r.content
        else:
            ret = r.content
        return ret

    def do_get(self, loc):
        self.logger.debug(self.get_url(loc))
        r = self.get(self.get_url(loc), headers=self.headers)
        return self.do_return(r)

    def do_post(self, loc, data, headers=None):
        if type(data) is dict:
            headers={'content-type': 'application/json'}
            data = json.dumps(data)
        r = self.post(self.get_url(loc), data=data, headers=headers)
        return self.do_return(r)

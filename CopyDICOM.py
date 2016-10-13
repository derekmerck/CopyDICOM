import logging
import argparse
import collections
from SessionWrapper import Session
from StructuredTags import simplify_tags
from pprint import pformat
from datetime import datetime
import time
from bs4 import BeautifulSoup

def replicate_tags(opts):
    logging.info('Replicating tags to index.')

    # Time has to be absent, or passed in as epoch to be a valid request
    def epoch(dt):
        tt = dt.timetuple()
        return time.mktime(tt)

    src = Session(opts.src)
    _instances = src.do_get('instances')
    logging.info("Found {0} candidate instances.".format(len(_instances)))

    index = Session(opts.index)

    index.scheme = "https"
    index.port = 8089
    index.auth = ('admin', 'splunk')
    r = index.do_post('services/search/jobs', data="search=search index=dicom | spath ID | dedup ID | table ID")
    soup = BeautifulSoup(r, 'xml')
    sid = soup.find('sid').string
    time.sleep(5)
    r = index.do_get('services/search/jobs/{0}/results'.format(sid), params={'output_mode': 'csv', 'count': 0})
    indexed_instances = r.replace('"', '').splitlines()[1:]
    logging.info("Found {0} instances already indexed.".format(len(indexed_instances)))
    instances = set(_instances) - set(indexed_instances)
    logging.info("Found {0} new instances to index.".format(len(instances)))

    # HEC uses strange token authorization
    headers = {'Authorization': 'Splunk A02CFC83-3AD4-4FA4-AD8B-26EA3F229B48'}
    index.scheme = "http"
    index.port = 8088
    index.auth = None

    for instance in instances:
        tags = src.do_get('instances/{0}/simplified-tags'.format(instance))
        simplified_tags = simplify_tags(tags)
        # Add Orthanc ID for future reference
        simplified_tags['ID'] = instance
        data = collections.OrderedDict([('time', epoch(simplified_tags['InstanceCreationDateTime'])),
                                        ('host', '{0}:{1}'.format(src.hostname, src.port)),
                                        ('sourcetype', '_json'),
                                        ('index', 'dicom'),
                                        ('event', simplified_tags )])
        # logging.debug(pformat(data))
        index.do_post('services/collector/event', data=data, headers=headers)


def copy_instances(src, dest, _instances):

    dest_instances = dest.do_get('instances')
    instances = set(_instances) - set(dest_instances)
    logging.debug('Found {0} new instances out of {1}'.format(len(instances), len(_instances)))

    for instance in instances:
        dicom = src.do_get('instances/{0}/file'.format(instance))
        headers = {'content-type': 'application/dicom'}
        dest.do_post('instances', data=dicom, headers=headers)


def conditional_replicate(opts):

    def FilterInstances():
        index = Session(opts.index)
        instances = index.do_put(opts.query)
        # TODO: Figure out what these queries will look like
        return instances

    src = Session(opts.src)
    dest = Session(opts.dest)
    instances = FilterInstances()
    # TODO: Confirm those instances exist on src
    copy_instances(src, dest, instances)


def replicate(opts):
    src = Session(opts.src)
    dest = Session(opts.dest)
    instances = src.do_get('instances')
    copy_instances(src, dest, instances)


def parse_args(args):

    # create the top-level parser
    parser = argparse.ArgumentParser(prog='CopyDICOM')
    subparsers = parser.add_subparsers()

    parser_a = subparsers.add_parser('replicate',
                                     help='Copy non-redundant images from one Orthanc to another.')
    parser_a.add_argument('--src')
    parser_a.add_argument('--dest')
    parser_a.set_defaults(func=replicate)

    parser_b = subparsers.add_parser('replicate_tags',
                                     help='Copy non-redundant tags from one Orthanc instance to a Splunk index.')
    parser_b.add_argument('--src')
    parser_b.add_argument('--index')
    parser_b.set_defaults(func=replicate_tags)

    parser_c = subparsers.add_parser('conditional_replicate',
                                     help='Copy non-redundant images one Orthanc to another using an index filter')
    parser_c.add_argument('--src')
    parser_c.add_argument('--dest')
    parser_c.add_argument('--index')
    parser_c.add_argument('--query')
    parser_c.set_defaults(func=conditional_replicate)

    return parser.parse_args(args)





if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)

    # opts = parse_args(['replicate',
    #                    '--src',  'http://orthanc:orthanc@localhost:8042',
    #                    '--dest', 'http://orthanc:orthanc@localhost:8043'])

    opts = parse_args(['replicate_tags',
                       '--src',  'http://orthanc:orthanc@localhost:8042',
                       '--index', 'http://Splunk:C7012473-4101-49E2-88EF-83AA2A78FCC2@localhost:8088'])
    #
    # opts = parse_args(['replicate_tags',
    #                    '--src',   'http://orthanc:orthanc@localhost:8042',
    #                    '--index', 'http://admin:splunk@localhost:8088',
    #                    '--query', 'SeriesDescription=\'Dose Record\''
    #                    '--dest',  'http://orthanc:orthanc@localhost:8043'])

    logging.debug(opts)
    opts.func(opts)

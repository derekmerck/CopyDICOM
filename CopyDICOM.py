import logging
import argparse
import collections
from SessionWrapper import Session
from StructuredTags import simplify_tags
from bs4 import BeautifulSoup
from hashlib import md5
import time
import pprint


def indexed_instances(index, q=None):

    def poll_until_done(sid):
        isDone = False
        i = 0
        while not isDone:
            i = i + 1
            time.sleep(1)
            r = index.do_get('services/search/jobs/{0}'.format(sid), params={'output_mode': 'json'})
            isDone = r['entry'][0]['content']['isDone']
            status = r['entry'][0]['content']['dispatchState']
            if i % 5 == 1:
                logging.debug('Waiting to finish {0} ({1})'.format(i, status))
        return r['entry'][0]['content']['resultCount']

    if not q:
        q = "search index=dicom | spath ID | dedup ID | table ID"

    r = index.do_post('services/search/jobs', data="search={0}".format(q))
    soup = BeautifulSoup(r, 'xml')
    sid = soup.find('sid').string

    n = poll_until_done(sid)
    offset = 0
    instances = []
    i = 0
    while offset < n:
        count = 50000
        offset = 0 + count*i
        r = index.do_get('services/search/jobs/{0}/results'.format(sid), params={'output_mode': 'csv', 'count': count, 'offset': offset})
        instances = instances + r.replace('"', '').splitlines()[1:]
        i = i+1

    return instances


def replicate_dose_tags(opts):
    logging.info('Replicating dose report tags to index.')

    # Time has to be absent, or passed in as epoch to be a valid request
    def epoch(dt):
        tt = dt.timetuple()
        return time.mktime(tt)

    src = Session(opts.src)
    # all_series = src.do_get('series')

    # Get only RECENT series
    all_series = src.do_post('tools/find', data={'Level': 'Series',
                                                 'Query': {'StudyDate': '20170112-'}})
    logging.info("Found {0} candidate series.".format(len(all_series)))
    _instances = []

    for i, series in enumerate(all_series):
        summary = src.do_get('series/{0}'.format(series))
        # logging.debug(pprint.pformat(summary))
        # TODO: Need to check for GE=997 or SYNGO=502
        if summary['MainDicomTags']['SeriesNumber'] == '997' or summary['MainDicomTags']['SeriesNumber'] == '502':
            _instances.append(summary['Instances'][0])
        logging.info("Found {0} dose report (997) instances of {1} in {2}.".format(len(_instances), i, len(all_series)))
        # if len(_instances) > 60: break

    index = Session(opts.index)

    _indexed_instances = indexed_instances(index)
    logging.info("Found {0} instances already indexed.".format(len(_indexed_instances)))

    instances = set(_instances) - set(_indexed_instances)
    logging.info("Found {0} new instances to index.".format(len(instances)))

    # HEC uses strange token authorization
    hec = Session(opts.hec)

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
        hec.do_post('services/collector/event', data=data)



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

    _indexed_instances = indexed_instances(index)
    logging.info("Found {0} instances already indexed.".format(len(_indexed_instances)))

    instances = set(_instances) - set(_indexed_instances)
    logging.info("Found {0} new instances to index.".format(len(instances)))

    # HEC uses strange token authorization
    hec = Session(opts.hec)

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
        hec.do_post('services/collector/event', data=data)


def copy_instances(src, dest, _instances):

    def get_instance(instance, anonymize=False):
        if not anonymize:
            return src.do_get('instances/{0}/file'.format(instance))
        else:
            # Have to hash the accession number and patient id
            tags = src.do_get('instances/{0}/simplified-tags'.format(instance))

            if tags.get('PatientIdentityRemoved') == "YES":
                # Already anonymized, return file
                return src.do_get('instances/{0}/file'.format(instance))
            else:
                # Anonymize with hashed PID and AID
                anon_pid = md5.new(tags['PatientID']).hexdigest()[:8]
                anon_aid = md5.new(tags['AccessionNumber']).hexdigest()[:8]
                anon_iid = md5.new(instance).hexdigest()[:8]

                return src.do_post('instances/{0}/anonymize'.format(instance),
                                    data={'Replace': {'PatientID': anon_pid,
                                                      'PatientName': anon_pid,
                                                      'AccessionNumber': anon_aid,
                                                      'DeidentificationMethod': 'Anonymized from ID {0}'.format(anon_iid)},
                                          'Keep':    ['StudyDescription',
                                                      'SeriesDescription']})

    # TODO: Also need to include the list of "Anonymized from" instances as polynyms
    dest_instances = dest.do_get('instances')
    instances = set(_instances) - set(dest_instances)
    logging.debug('Found {0} new instances out of {1}'.format(len(instances), len(_instances)))

    for instance in instances:
        dicom = get_instance(instance)
        headers = {'content-type': 'application/dicom'}
        dest.do_post('instances', data=dicom, headers=headers)


def conditional_replicate(opts):

    src = Session(opts.src)
    dest = Session(opts.dest)
    index = Session(opts.index)
    instances = indexed_instances(index, q=opts.query)
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
    parser_b.add_argument('--index', help="Splunk API address")
    parser_b.add_argument('--hec',   help="Splunk HEC address")
    parser_b.set_defaults(func=replicate_tags)

    parser_b = subparsers.add_parser('replicate_dose_tags',
                                     help='Copy non-redundant dose report tags from one Orthanc instance to a Splunk index.')
    parser_b.add_argument('--src')
    parser_b.add_argument('--index', help="Splunk API address")
    parser_b.add_argument('--hec',   help="Splunk HEC address")
    parser_b.set_defaults(func=replicate_dose_tags)

    parser_c = subparsers.add_parser('conditional_replicate',
                                     help='Copy non-redundant images one Orthanc to another using an index filter')
    parser_c.add_argument('--src')
    parser_c.add_argument('--index')
    parser_c.add_argument('--query')
    parser_c.add_argument('--dest')
    parser_c.set_defaults(func=conditional_replicate)

    return parser.parse_args(args)


if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)

    # Test mirroring
    opts = parse_args(['replicate',
                       '--src',  'http://orthanc:orthanc@localhost:8042',
                       '--dest', 'http://orthanc:orthanc@localhost:8043'])

    logging.debug(opts)
    opts.func(opts)

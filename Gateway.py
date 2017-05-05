from SessionWrapper import Session
from StructuredTags import simplify_tags, normalize_ctdi_tags
import collections
import logging
from bs4 import BeautifulSoup
import time
import pprint
import hashlib

class Gateway(object):

    def __init__(self, *args, **kwargs):
        super(Gateway, self).__init__()
        # Create session wrapper
        address = kwargs.get('address')
        self.session = Session(address)
        # self.base_uuid = uuid.uuid3(uuid.NAMESPACE_DNS, 'cirr.lifespan.org')

    def ListItems(self, condition=None, *args, **kwargs):
        raise NotImplementedError

    def GetItem(self, *args, **kwargs):
        raise NotImplementedError

    def AddItem(self, item, *args, **kwargs):
        raise NotImplementedError


class OrthancGateway(Gateway):

    def __init__(self, *args, **kwargs):
        super(OrthancGateway, self).__init__(**kwargs)
        # Active level
        self.level = kwargs.get('level')

    def QueryRemote(self, remote, query=None, *args, **kwargs):

        data = {'Level': self.level,
                'Query': query}

        r = self.session.do_post('modalities/{0}/query'.format(remote), data=data)
        return r

    def RetrieveFromRemote(self, remote, resources=None):
        data = {'Level': self.level,
                'Resources': resources}

        logging.debug(pprint.pformat(data))

        r = self.session.do_post('modalities/{0}/move'.format(remote), data=data)

        return r

    def ListItems(self, condition=None, *args, **kwargs):

        if condition:
            raise NotImplementedError

        r = self.session.do_get(self.level)
        logging.info("Found {0} candidate {1}.".format(len(r), self.level))
        return r

    def GetItem(self, item, dtype="tags"):

        r = None
        if dtype=="tags":
            if self.level == 'instances':
                r = self.session.do_get('{0}/{1}/tags?simplify'.format(self.level, item))
            else:
                r = self.session.do_get('{0}/{1}/shared-tags?simplify'.format(self.level, item))
            r = simplify_tags(r)
            # Add item ID for later reference
            r['ID'] = item

            # logging.debug(pprint.pformat(r))

        elif dtype=="info":
            r = self.session.do_get('{0}/{1}'.format(self.level, item))

        elif dtype=="file":
            r = self.session.do_get('{0}/{1}/file'.format(self.level, item))
        return r

    def AddItem(self, item, *args, **kwargs):
        if self.level != "instances":
            raise NotImplementedError
        headers = {'content-type': 'application/dicom'}
        self.session.do_post('instances', data=item, headers=headers)


class SplunkGateway(Gateway):

    def __init__(self, *args, **kwargs):
        super(SplunkGateway, self).__init__(**kwargs)
        self.hec_address = kwargs.get('hec_address')
        if self.hec_address:
            self.hec = Session(self.hec_address)
        # Active index name
        self.index = kwargs.get('index')
        # Mapping between functions and index names
        self.index_names = kwargs.get('index_names',
                                      {'series': 'dicom_series',
                                       'dose': 'dose_reports',
                                       'remote_studies': 'pacs_studies',
                                       'remote_series': 'pacs_series'})

    def ListItems(self, condition=None, *args, **kwargs):

        def poll_until_done(sid):
            isDone = False
            i = 0
            r = None
            while not isDone:
                i = i + 1
                time.sleep(1)
                r = self.session.do_get('services/search/jobs/{0}'.format(sid), params={'output_mode': 'json'})
                isDone = r['entry'][0]['content']['isDone']
                status = r['entry'][0]['content']['dispatchState']
                if i % 5 == 1:
                    logging.debug('Waiting to finish {0} ({1})'.format(i, status))
            return r['entry'][0]['content']['resultCount']

        if not condition:
            condition = "search index={0} | spath ID | dedup ID | table ID".format(self.index)

        r = self.session.do_post('services/search/jobs', data="search={0}".format(condition))
        soup = BeautifulSoup(r, 'xml')
        sid = soup.find('sid').string
        n = poll_until_done(sid)
        offset = 0
        instances = []
        i = 0
        while offset < n:
            count = 50000
            offset = 0 + count * i
            r = self.session.do_get('services/search/jobs/{0}/results'.format(sid),
                             params={'output_mode': 'csv', 'count': count, 'offset': offset})
            instances = instances + r.replace('"', '').splitlines()[1:]
            i = i + 1
        return instances

    def AddItem(self, item, *args, **kwargs):

        def epoch(dt):
            tt = dt.timetuple()
            return time.mktime(tt)

        src = kwargs.get('src')
        host = kwargs.get('host', '{0}:{1}'.format(src.session.hostname, src.session.port))

        data = collections.OrderedDict([('time', epoch(item['InstanceCreationDateTime'])),
                                        ('host', host),
                                        ('sourcetype', '_json'),
                                        ('index', self.index),
                                        ('event', item)])
        # logging.debug(pformat(data))
        self.hec.do_post('services/collector/event', data=data)


def SetDiff( items1, items2 ):
    if not items2:
        return items1
    return set(items1) - set(items2)


def CopyItems( src, dest, items, dtype='tags' ):

    if not items:
        logging.info('Nothing to copy')
        return

    logging.debug('Items to copy:')
    logging.debug(pprint.pformat(items))

    for item in items:
        data = src.GetItem(item, dtype)
        dest.AddItem(data, src=src)


def CopyNewItems( src, dest, items, dtype='tags' ):
    new_items = SetDiff(items, dest.ListItems() )

    logging.debug('New items:')
    logging.debug(pprint.pformat(new_items))

    CopyItems(src, dest, new_items, dtype)


def UpdateSeriesIndex( orthanc, splunk ):
    orthanc.level = 'series'
    splunk.index = splunk.index_names['series']
    items = orthanc.ListItems()

    logging.debug('Candidate items:')
    logging.debug(pprint.pformat(items))

    CopyNewItems( orthanc, splunk, items, 'tags' )



# Doing this hour-by-hour results in a complete list of studies for the day
# DOES include outside studies
# DOES include incomplete or cancelled studies
# DOES NOT include OFFLINE studies
# This _should_ be more than whatever is in the dose index, as it will include outside studies.

def UpdateRemoteStudyIndex( orthanc, remote, splunk, **kwargs ):
    orthanc.level = 'study'
    splunk.index = splunk.index_names['remote_studies']

    existing_items = splunk.ListItems()
    # logging.debug(existing_items)

    study_date = kwargs.get('study_date')
    study_time = kwargs.get('study_time')
    modality = kwargs.get('modality', 'CT')

    # Have to request all fields that you want returned (see DICOM std table C.6-5)
    q = orthanc.QueryRemote(remote, query={'StudyDate': study_date,
                                           'AccessionNumber':'',
                                           'ModalitiesInStudy':modality,
                                           'PatientBirthDate':'',
                                           'NumberOfSeries':'',
                                           'PatientID':'',
                                           'PatientName':'',
                                           'PatientSex':'',
                                           'ReferringPhysicianName': '',
                                           'StudyTime':study_time,
                                           'StudyDescription':''})
    logging.debug(pprint.pformat(q))

    answers = orthanc.session.do_get('queries/{0}/answers/'.format(q['ID']))

    # logging.debug(pprint.pformat(answers))
    # logging.debug("Found {0} answers".format(len(answers)))

    host = '{0}:{1}/modalities/{2}'.format(orthanc.session.hostname, orthanc.session.port, remote)
    # accessions = []

    for a in answers:
        r = orthanc.session.do_get('queries/{0}/answers/{1}/content?simplify'.format(q['ID'],a))
        r = simplify_tags(r)

        s = hashlib.sha1("{0}{1}".format(str(r['PatientID']), str(r['StudyInstanceUID']))).hexdigest()
        r['ID'] = '-'.join(s[i:i+8] for i in range(0, len(s), 8))

        logging.debug(pprint.pformat(r))

        if not str(r['ID']) in existing_items:
            logging.debug('Adding item {0}'.format(r['ID']))
            splunk.AddItem(r, src=orthanc, host=host)
            # accessions.append(r['AccessionNumber'])
        else:
            logging.debug('Skipping item {0}'.format(r['ID']))

    # logging.debug(accessions)
    # logging.debug("Found {0} studies to index".format(len(accessions)))
    #
    # return len(accessions)


def UpdateRemoteSeriesIndex( orthanc, remote, splunk, **kwargs ):

    # Query the study index to get a list of candidate accession numbers
    # Query the series index to eliminate series that have already been indexed
    # Query remote for each candidate accession number to get basic DICOM tags

    orthanc.level = 'series'
    splunk.index = splunk.index_names['remote_series']

    # existing_items = splunk.ListItems()
    # logging.debug(existing_items)

    accession_number = kwargs.get('accession_number')

    # Have to request all fields that you want returned (see DICOM std table C.6-5)
    q = orthanc.QueryRemote(remote, query={'StudyDate': '',
                                           'AccessionNumber':accession_number,
                                           'InstitutionName':'',
                                           'Modality':'',
                                           'ModalitiesInStudy':'',
                                           'PatientBirthDate':'',
                                           'NumberOfSeries':'',
                                           'PatientID':'',
                                           'PatientName':'',
                                           'PatientSex':'',
                                           'ReferringPhysicianName': '',
                                           'StationName':'',
                                           'SeriesDescription':'',
                                           'StudyTime':'',
                                           'StudyDescription':''})
    logging.debug(pprint.pformat(q))

    answers = orthanc.session.do_get('queries/{0}/answers/'.format(q['ID']))

    host = '{0}:{1}/modalities/{2}'.format(orthanc.session.hostname, orthanc.session.port, remote)
    # accessions = []

    r = None

    # Review all series for this study
    for a in answers:
        r = orthanc.session.do_get('queries/{0}/answers/{1}/content?simplify'.format(q['ID'],a))
        r = simplify_tags(r)

        logging.debug(pprint.pformat(r))

        # r = orthanc.session.do_post('queries/{0}/answers/{1}/retrieve'.format(q['ID'], a), data='DEATHSTAR')

    siuid = r['SeriesInstanceUID']
    orthanc.level = 'Instance'

    # Have to request all fields that you want returned (see DICOM std table C.6-5)
    q = orthanc.QueryRemote(remote, query={'StudyDate': '',
                                           'AccessionNumber':'',
                                           'InstitutionName':'',
                                           'Modality':'',
                                           'PatientBirthDate':'',
                                           'NumberOfSeries':'',
                                           'PatientID':'',
                                           'PatientName':'',
                                           'PatientSex':'',
                                           'ReferringPhysicianName':'',
                                           'StationName':'',
                                           'SeriesDescription':'',
                                           'SeriesInstanceUID': siuid,
                                           'StudyTime':'',
                                           'StudyDescription':''})
    logging.debug(pprint.pformat(q))


    answers = orthanc.session.do_get('queries/{0}/answers/'.format(q['ID']))

    # Review all instances in this series
    for a in answers:
        r = orthanc.session.do_get('queries/{0}/answers/{1}/content?simplify'.format(q['ID'], a))
        r = simplify_tags(r)

        logging.debug(pprint.pformat(r))

        # r = orthanc.session.do_post('queries/{0}/answers/{1}/retrieve'.format(q['ID'], a), data='DEATHSTAR')


    # Pull a single instance for review (this doesn't work)
    orthanc.level = 'instance'

    stiuid = r['StudyInstanceUID']
    siuid = r['SeriesInstanceUID']
    sopiuid = r['SOPInstanceUID']

    r = orthanc.RetrieveFromRemote(remote, resources=[{
                                                         'StudyInstanceUID':stiuid,
                                                         'SeriesInstanceUID':siuid,
                                                         'SOPInstanceUID': sopiuid
                                                       }])

    logging.debug(pprint.pformat(r))


def UpdateDoseReports( orthanc, splunk ):

    # List of candidate series out of Splunk/dicom_series
    splunk.index = splunk.index_names['series']
    # Can limit the search with "earliest=-2d" for example
    q = "search index={0} SeriesNumber = 997 OR SeriesNumber = 502 | table ID".format(splunk.index)
    candidates = splunk.ListItems(q)

    # Which ones are already available in Splunk/dose_records (looking at ParentSeriesID)
    splunk.index = splunk.index_names['dose']
    q = "search index={0} | table ParentSeriesID".format(splunk.index)
    indexed = splunk.ListItems(q)

    items = SetDiff(candidates, indexed)

    # logging.debug(pprint.pformat(candidates))
    # logging.debug(pprint.pformat(indexed))
    # logging.debug(pprint.pformat(items))

    # Get instance from Orthanc
    for item in items:
        orthanc.level = 'series'
        info = orthanc.GetItem(item, 'info')
        instance = info['Instances'][0]

        orthanc.level = 'instances'
        tags = orthanc.GetItem(instance, 'tags')
        # Add IDs
        tags['ParentSeriesID'] = item

        # Normalize missing CTDIvol tags
        tags = normalize_ctdi_tags(tags)

        logging.debug(pprint.pformat(tags))

        splunk.AddItem(tags, src=orthanc)

    logging.debug('Candidate dose reports: {0}'.format(len(candidates)))
    logging.debug('Indexed dose reports: {0}'.format(len(indexed)))
    logging.debug('New dose reports: {0}'.format(len(items)))


if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)

    orthanc0_address = "http://orthanc:orthanc@localhost:8042"
    orthanc1_address = "http://orthanc:orthanc@localhost:8043"
    splunk_address   = "https://admin:splunk@localhost:8089"
    hec_address      = "http://Splunk:token@localhost:8088"

    splunk = SplunkGateway(address=splunk_address,
                           hec_address=hec_address)
    orthanc0 = OrthancGateway(address=orthanc0_address)
    orthanc1 = OrthancGateway(address=orthanc1_address)

    # Update the series index
    UpdateSeriesIndex(orthanc0, splunk)

    # Update the dose reports based on the splunk index
    UpdateDoseReports(orthanc0, splunk)


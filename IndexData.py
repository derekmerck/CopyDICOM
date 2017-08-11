import logging
from pprint import pformat
from io import BytesIO
import json
import time
import datetime

from MeasureScout import MeasureScout

def UpdatePatientDimensions( orthanc, splunk ):
    '''Queries Splunk for unsized localizers and measures them'''

    # List of candidate series out of Splunk/dicom_series
    splunk.index = splunk.index_names['series']
    # Can limit the search with "earliest=-2d" for example
    q = "search index={0} Modality=CT ImageType=\"*LOCALIZER*\" | table AccessionNumber SeriesNumber ID | join type=left [search index=patient_dims | table AccessionNumber AP_dim Lat_dim ] | where isnull(AP_dim) | fields - AccessionNumber SeriesNumber AP_dim".format(splunk.index)
    items = splunk.ListItems(q)

    for i in range(0,len(items)):
        items[i] = items[i].replace(',', '')

    logging.debug(pformat(items))

    results = {}

    # Get instance from Orthanc
    for item in items:
        orthanc.level = 'series'
        info = orthanc.GetItem(item, 'info')

        logging.debug(info)

        orthanc.level = 'instances'
        for instance in info['Instances']:

            data = orthanc.GetItem(instance, 'file')

            ret = MeasureScout(BytesIO(data))

            logging.debug(pformat(ret))
            ret["ID"] = instance
            ret["InstanceCreationDateTime"] = datetime.datetime.now()

            splunk.index = splunk.index_names['patient_dims']
            splunk.AddItem(ret, src=orthanc)

    #         if not results.get(ret['AccessionNumber']):
    #             results[ret['AccessionNumber']] = ret
    #         else:
    #             results[ret['AccessionNumber']].update(ret)
    #
    # json.dump(results.values(), open('/Users/derek/Desktop/scouts.json', 'w'))
    # logging.debug(pformat(results))


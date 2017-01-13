import logging
# import requests
import json
from datetime import datetime
from pprint import pprint, pformat


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)


# DICOM Date/Time format
def get_datetime(s):
    try:
        # GE Scanner aggregated dt format
        ts = datetime.strptime(s, "%Y%m%d%H%M%S")
    except ValueError:
        # Siemens scanners use a slightly different aggregated format with fractional seconds
        ts = datetime.strptime(s, "%Y%m%d%H%M%S.%f")
    return ts


# def get_tags(item):
#
#     ORTHANC_HOST = "http://localhost:8042"
#     USER = "orthanc"
#     PASS = "orthanc"
#
#     url = ORTHANC_HOST + '/instances/' + item + '/simplified-tags'
#     r = requests.get(url, auth=(USER, PASS))
#     tags = r.json()
#
#     # Stash data for later
#     fn = item[0:4]
#     with open("samples/" + fn + ".json", 'w') as f:
#         json.dump(tags, f, indent=3, cls=DateTimeEncoder, sort_keys=True)
#
#     return tags


def simplify_structured_tags(tags):

    data = {}

    for item in tags["ContentSequence"]:

        # logging.debug('Item = ' + pformat(item))

        try:
            key = item['ConceptNameCodeSequence'][0]['CodeMeaning']
            type_ = item['ValueType']
            value = None
        except KeyError:
            logging.debug('No key or no type, returning')
            return

        if type_ == "TEXT":
            value = item['TextValue']
            # logging.debug('Found text value')
        elif type_ == "NUM":
            value = float(item['MeasuredValueSequence'][0]['NumericValue'])
            # logging.debug('Found numeric value')
        elif type_ == 'UIDREF':
            value = item['UID']
            # logging.debug('Found uid value')
        elif type_ == 'DATETIME':
            value = get_datetime(item['DateTime'])
            # logging.debug('Found date/time value')
        elif type_ == 'CODE':
            value = item['ConceptCodeSequence'][0]['CodeMeaning']
            # logging.debug('Found coded value')
        elif type_ == "CONTAINER":
            value = simplify_structured_tags(item)
            # logging.debug('Found container - recursing')
        else:
            logging.debug("Unknown ValueType (" + item['ValueType'] + ")")

        if data.get(key):
            logging.debug('Key already exists (' + key + ')')
            if isinstance(data.get(key), list):
                value = data[key] + [value]
                # logging.debug('Already a list, so appending')
            else:
                value = [data[key], value]
                # logging.debug('Creating a list from previous and current')

        data[key] = value

    return data


def simplify_tags(tags):

    # Parse any structured data into simplified tag structure
    if tags.get('ConceptNameCodeSequence'):
        # There is structured data in here
        key = tags['ConceptNameCodeSequence'][0]['CodeMeaning']
        value = simplify_structured_tags(tags)

        t = get_datetime(tags['ContentDate'] + tags['ContentTime'])
        value['ContentDateTime'] = t

        del(tags['ConceptNameCodeSequence'])
        del(tags['ContentSequence'])
        del(tags['ContentDate'])
        del(tags['ContentTime'])

        tags[key] = value

    # Convert DICOM DateTimes into ISO DateTimes
    t = get_datetime(tags['StudyDate'] + tags['StudyTime'])
    tags['StudyDateTime'] = t

    try:
        t = get_datetime(tags['SeriesDate'] + tags['SeriesTime'])
        tags['SeriesDateTime'] = t
    except KeyError:
        pass

    # Not all instances have ObservationDateTime
    try:
        t = get_datetime(tags['ObservationDateTime'])
        tags['ObservationDateTime'] = t
    except KeyError:
        pass

    # Not all instances have an InstanceCreationDate
    try:
        t = get_datetime(tags['InstanceCreationDate'] + tags['InstanceCreationTime'])
        tags['InstanceCreationDateTime'] = t
    except KeyError:
        pass

    # We want to use InstanceCreationDate as the _time field, so put a sensible value in if it's missing
    if not tags.get('InstanceCreationDateTime'):
        if tags.get('SeriesDateTime'):
            tags['InstanceCreationDateTime'] = tags['SeriesDateTime']
        else:
            tags['InstanceCreationDateTime'] = tags['StudyDateTime']

    # logging.info(pformat(tags))

    return tags


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    # items = ['dffa86e4-77265848-38fc0072-e9566534-d3d06bc8',
    #          'ab557aef-637dacbd-9b6677ef-a5890f51-a1992a49',
    #          '7dcd0529-8e5bfe27-118509b8-a37775f9-d780c34a',
    #          '07e06a17-44ae190d-43513b70-31566585-7928a9ce',
    #          '900ca1e1-331a5cac-427a8455-36a7b2d7-626ac3db',
    #          'e84ddaf2-0c0eb06c-bfd2371b-f42bb1a4-029c9ba1']
    #
    # for item in items:
    #     tags = get_tags(item)

    items = ["dffa", 'ab55', '7dcd', '07e0', '900c', 'e84d']

    for item in items:

        with open('samples/{0}.json'.format(item)) as f:
            tags = json.load(f)

        tags = simplify_tags(tags)

        with open('samples/{0}-simple.json'.format(item), 'w') as f:
            json.dump(tags, f, indent=3, cls=DateTimeEncoder, sort_keys=True)


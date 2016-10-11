import logging
import argparse
from OrthancSession import OrthancSession
from SplunkSession import SplunkSession
from StructuredTags import simplify_tags


def ReplicateTags(args):

    src = OrthancSession(args.src)
    index = SplunkSession(args.index)

    instances = src.do_get('instances')
    # TODO: Figure out which instances are already in index

    for instance in instances:
        tags = src.do_get('instances/{0}/simplified-tags'.format(instance))
        simplified_tags = simplify_tags(tags)
        # TODO: Add instance_id to tags
        index.do_put(simplified_tags)


def copy_instances(src, dest, _instances):

    dest_instances = dest.do_get('instances')
    instances = set(_instances) - set(dest_instances)
    logging.debug('Found {0} new instances out of {1}'.format(len(instances), len(src_instances)))

    for instance in instances:
        dicom = src.do_get('instances/{0}/file'.format(instance))
        headers = {'content-type': 'application/dicom'}
        dest.do_post('instances', data=dicom, headers=headers)


def ConditionalReplicate(src, dest, index, filter):

    def FilterInstances(index, filter):
        # TODO: Figure out what these Splunk queries will look like
        pass

    src = OrthancSession(args.src)
    dest = OrthancSession(args.dest)
    instances = FilterInstances(index, filter)
    # TODO: Confirm those instances exist on src
    copy_instances(src, dest, instances)


def Replicate(args):
    src = OrthancSession(args.src)
    dest = OrthancSession(args.dest)
    instances = src.do_get('instances')
    copy_instances(src, dest, instances)


def parse_args(args):

    # create the top-level parser
    parser = argparse.ArgumentParser(prog='CopyDICOM',
                                     help='Copy DICOM tags and images from one Orthanc to elsewhere.')
    subparsers = parser.add_subparsers()

    parser_a = subparsers.add_parser('replicate',
                                     help='Copy non-redundant images from one Orthanc to another.')
    parser_a.add_argument('--src')
    parser_a.add_argument('--dest')
    parser_a.set_defaults(func=Replicate)

    parser_b = subparsers.add_parser('replicate_tags',
                                     help='Copy non-redundant tags from one Orthanc instance to a Splunk index.')
    parser_b.add_argument('--src')
    parser_b.add_argument('--index')
    parser_b.set_defaults(func=ReplicateTags)

    parser_c = subparsers.add_parser('conditional_replicate',
                                     help='Copy non-redundant images one Orthanc to another using an index filter')
    parser_c.add_argument('--src')
    parser_c.add_argument('--dest')
    parser_c.add_argument('--index')
    parser_c.add_argument('--filter')
    parser_c.set_defaults(func=ConditionalReplicate)

    return parser.parse_args(args)


if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)

    args = parse_args(['replicate',
                       '--src',  'http://orthanc:orthanc@localhost:8042',
                       '--dest', 'http://orthanc:orthanc@localhost:8043'])

    args = parse_args(['replicate_tags',
                       '--src',  'http://orthanc:orthanc@localhost:8042',
                       '--index', 'http://admin:splunk@localhost:8088'])

    logging.debug(args)
    args.func(args)

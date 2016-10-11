# CopyDICOM

[Derek Merck](email:derek_merck@brown.edu)  

<https://github.com/derekmerck/CopyDICOM>


## Overview

`CopyDICOM` is a python script that monitors an installation of Jodogne's [Orthanc][] and copies DICOM imaging to another instance of Orthanc or DICOM tags to a [Splunk][] index.  It can also reduce DICOM structured report tags into a format following Orthanc's 'simplified-tags' presentation.  This can be useful for parsing data from dose reports into a data index.

`CopyDICOM` is intended to be used as an adjunct with an automatic DICOM data analytics framework, specifically [DIANA][], but it works well as a stand alone tool, with somewhat more intelligent copying than Orthanc's standard `Replicate.py` script.
 
 [Orthanc]: https://orthanc.chu.ulg.ac.be
 [DICOM]: http://dicom.nema.org
 [Splunk]: https://www.splunk.com
 [DIANA]: https://github.com/derekmerck/miip


## Dependencies

- Python 2.7
- Requests


## Usage

To use it as a stand-alone script:

````bash
$ docker run docker run -d -p 8042:8042 jodogne/orthanc
$ docker run docker run -d -p 8043:8042 jodogne/orthanc
$ python CopyDICOM.py replicate --src 'http://orthanc:orthanc@localhost:8042' \
>  --dest 'http://orthanc:orthanc@localhost:8043'
````

````bash
$ docker run docker run -d -p 8088:8088 outcoldman/splunk
$ python CopyDICOM.py replicate_tags --src 'http://orthanc:orthanc@localhost:8042' \
>  --index 'http://admin:changeme@localhost:8088'
````

````bash
$ python CopyDICOM.py conditional_replicate --src 'http://orthanc:orthanc@localhost:8042' \
>  --index 'http://admin:changeme@localhost:8088' --query 'SeriesDescription=\'Dose Record\'' \ 
>  --dest 'http://orthanc:orthanc@localhost:8043'
````

To use it as a Python library in a script:

````python
>>> import CopyDICOM
>>> CopyDICOM.replicate('http://orthanc:orthanc@localhost:8042', 'http://orthanc:orthanc@localhost:8043')
````


## Functionality

* `replicate`: copy all non-duplicate DICOM images from a source Orthanc instance to a destination Orthanc instance
* `replicate_tags`: copy all non-duplicate DICOM tags from a source Orthanc instance to a Splunk index
* `conditional_replicate`: Query a Splunk index for a set of candidate instances, and copy non-duplicate DICOM images in this set from a source Orthanc instance to a destination Orthanc instance.

`conditional_replicate` is intended to allow automatic duplication of specific image types from a primary archive into secondary, project specific DICOM stores, typically with a de-identifier on ingestion.  In DIANA, such secondary image repositories are called "Anonymized Image Archives" or "AIRs".


## Utilization and Dose Reporting with Splunk

A simple Splunk query can create a _Count of Studies by Modality by Day_ dashboard from the tag data.

If structured dose reports are included in the archive monitored by `CopyDICOM replicate_tags`, the dose data will also be available for a Splunk dashboard, such as reviewing _Dose by Protocol_.  This is a particularly useful function to the Diagnostic Imaging department at RIH for auditing our quarterly ACR Dose Reports.


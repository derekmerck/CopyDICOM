'''Measure AP and Lateral dimensions from DICOM localizer images for SSDE calculations'''

import dicom
import logging
import numpy as np
# from matplotlib import pyplot as plt
from pprint import pformat
from sklearn.mixture import GMM
import json
import glob

def MeasureScout(fp):

    # Read DICOM file and info
    # Get ref file
    dcm = dicom.read_file(fp)

    # Load spacing values (in mm)
    pixel_spacing = (float(dcm.PixelSpacing[0]), float(dcm.PixelSpacing[1]))

    # Load study info
    patient_name = dcm.PatientName
    accession_number = dcm.AccessionNumber

    # Determine measurement dimension
    orientation = dcm.ImageOrientationPatient

    if orientation[0]*orientation[0] > 0.2:
        # This is a PA scout, which gives the lateral measurement
        measured_dim = 'lateral_dim'
    elif orientation[1]*orientation[1] > 0.2:
        # This is a lateral scout, which gives the AP measurement
        measured_dim = 'AP_dim'
    else:
        measured_dim = 'Unknown_dim'

    # Setup pixel array data
    dcm_px = np.array(dcm.pixel_array, dtype=np.float32)

    # Determine weighted threshold separating tissue/non-tissue attenuations
    # using a GMM
    thresh = np.mean(dcm_px[dcm_px>0])

    gmm = GMM(2).fit(dcm_px[dcm_px>0].reshape(-1,1))
    thresh = np.sum(gmm.weights_[::-1]*gmm.means_.ravel())

    # logging.debug(gmm.weights_[::-1])
    # logging.debug(gmm.means_.ravel())

    logging.debug("Threshold: {0}".format(thresh))

    # Compute avg width based on unmasked pixels
    mask = dcm_px > thresh

    px_counts = np.sum(mask,axis=1)
    avg_px_count = np.mean(px_counts[px_counts>0])
    d_avg = avg_px_count * pixel_spacing[0] / 10;

    logging.debug("Average {0} width: {1}".format(measured_dim, d_avg))

    # plt.imshow(mask)
    # plt.show()

    ret = {'PatientName': patient_name,
           'AccessionNumber': accession_number,
           measured_dim:  d_avg}

    return ret

if __name__=="__main__":

    logging.basicConfig(level=logging.DEBUG)

    results = {}

    dir = "/Users/derek/Desktop/scouts"
    which = [0,1]

    fns = glob.glob(dir+"/*dcm")
    # fp = fns[which]

    # for fp in [fns[i] for i in which]:
    for fp in fns:
        ret = MeasureScout(fp)
        if not results.get(ret['AccessionNumber']):
            results[ret['AccessionNumber']]=ret
        else:
            results[ret['AccessionNumber']].update(ret)

    json.dump(results.values(), open('/Users/derek/Desktop/scouts.json', 'w'))

    logging.debug(pformat(results))
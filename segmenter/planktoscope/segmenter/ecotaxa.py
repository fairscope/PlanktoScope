# Copyright (C) 2021 Romain Bazile
#
# This file is part of the PlanktoScope software.
#
# PlanktoScope is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PlanktoScope is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PlanktoScope.  If not, see <http://www.gnu.org/licenses/>.

# Logger library compatible with multiprocessing
from loguru import logger


import csv
import io
import json
import math
import numbers
import os
import zipfile

import numpy

"""
Example of metadata file received
{
  "sample_project": "Tara atlantique sud 2021",
  "sample_id": "Tara atlantique sud 2021_hsn_2021_01_22",
  "sample_ship": "TARA",
  "sample_operator": "DAVE",
  "sample_sampling_gear": "net_hsn",
  "sample_concentrated_sample_volume": 100,
  "acq_id": "Tara atlantique sud 2021_hsn_2021_01_22_1",
  "acq_instrument": "PlanktoScope v2.2",
  "acq_instrument_id": "Babane Batoukoa",
  "acq_celltype": 300,
  "acq_minimum_mesh": 20,
  "acq_maximum_mesh": 200,
  "acq_volume": "37.50",
  "acq_imaged_volume": "2.9320",
  "acq_fnumber_objective": 16,
  "acq_camera": "HQ Camera",
  "acq_nb_frame": 750,
  "acq_software": "PlanktoScope v2.2-cd03960",
  "object_date": "20210122",
  "object_time": "115300",
  "object_lat": "-21.6167",
  "object_lon": "-38.2667",
  "object_depth_min": 0,
  "object_depth_max": 1,
  "process_pixel": 1,
  "process_id": 1,
  "sample_gear_net_opening": 40,
  "object_date_end": "20210122",
  "object_time_end": "115800",
  "object_lat_end": "-21.6168",
  "object_lon_end": "-38.2668",
  "sample_total_volume": 0.019,
  "acq_local_datetime": "2020-12-28T01:03:38",
  "acq_camera_resolution": "4056 x 3040",
  "acq_camera_iso": 100,
  "acq_camera_shutter_speed": 1,
  "acq_uuid": "Pobolautoa Jouroacu Yepaoyoa Babane Batoukoa",
  "sample_uuid": "Pobo Raikoajou Roacuye Sune Babane Batoukoa",
  "objects": [
    {
      "name": "01_13_28_232066_0",
      "metadata": {
        "label": 0,
        "width": 29,
        "height": 80,
        "bx": 3566,
        "by": 558,
        "circ.": 0.23671615936018325,
        "area_exc": 1077,
        "area": 1164,
        "%area": 0.07474226804123707,
        "major": 84.35144817947639,
        "minor": 22.651130623883205,
        "y": 596.041782729805,
        "x": 3581.5199628597957,
        "convex_area": 1652,
        "perim.": 248.58073580374352,
        "elongation": 3.7239398589020882,
        "perimareaexc": 0.23080848264043038,
        "perimmajor": 2.9469646481330463,
        "circex": 0.21902345672759224,
        "angle": 87.22379495121363,
        "bounding_box_area": 2320,
        "eccentricity": 0.9632705408870905,
        "equivalent_diameter": 37.03078435139837,
        "euler_number": 0,
        "extent": 0.4642241379310345,
        "local_centroid_col": 15.51996285979573,
        "local_centroid_row": 38.041782729805014,
        "solidity": 0.6519370460048426,
        "MeanHue": 82.38316151202748,
        "MeanSaturation": 51.052405498281786,
        "MeanValue": 206.95103092783506,
        "StdHue": 59.40613253229589,
        "StdSaturation": 33.57478449681238,
        "StdValue": 45.56457794758993
      }
    },
    {
      "name": "01_13_28_232066_1",
      "metadata": {
        "label": 1,
        "width": 632,
        "height": 543,
        "bx": 2857,
        "by": 774,
        "circ.": 0.021738961926042914,
        "area_exc": 15748,
        "area": 15894,
        "%area": 0.009185856297974082,
        "major": 684.6802239233394,
        "minor": 463.2216914254333,
        "y": 1018.0638176276352,
        "x": 3103.476631953264,
        "convex_area": 208154,
        "perim.": 3031.113057309706,
        "elongation": 1.47808325170704,
        "perimareaexc": 0.19247606409129453,
        "perimmajor": 4.42704922882231,
        "circex": 0.021539270945723152,
        "angle": 30.838437768527037,
        "bounding_box_area": 343176,
        "eccentricity": 0.7363949729430449,
        "equivalent_diameter": 141.60147015652535,
        "euler_number": -2,
        "extent": 0.045888989906054035,
        "local_centroid_col": 246.4766319532639,
        "local_centroid_row": 244.06381762763525,
        "solidity": 0.07565552427529618,
        "MeanHue": 66.62765823581226,
        "MeanSaturation": 50.187051717629295,
        "MeanValue": 192.57524852145463,
        "StdHue": 63.69755322016918,
        "StdSaturation": 20.599500714199607,
        "StdValue": 28.169250980740102
      }
    }
  ]
}
"""


"""
Ecotaxa Export archive format
In a folder place:

image files

    Colour and 8-bits greyscale images are supported, in jpg, png,gif (possibly animated) formats.
a tsv (TAB separated file) which can be .txt or .tsv extension. File name must start with ecotaxa (ecotaxa*.txt or ecotaxa*.tsv)

    It contains the metadata for each image. This file can be created in a spreadsheet application (see formats and examples below).

        Line 1 contains column headers
        Line 2 contains data format codes; [f] for floats, [t] for text
        Line 3...n contain data for each image

The metadata and data for each image is organised in various levels (image, object, process, sample, etc.). All column names must be prefixed with the level name (img_***, object_***, etc.). Some common fields, used to filter data, must be named and sometimes formatted in a certain way (required format in blue), which is documented below. But, overall, the only two mandatory fields are img_file_name and object_id (in red).

    IMAGE
        img_file_name [t]: name of the image file in the folder (including extension)
        img_rank [f] : rank of image to be displayed, in case of existence of multiple (<10) images for one object. Starts at 1.
    OBJECT: one object to be classified, usually one organism. One object can be represented by several images. In this tsv file, there is one line per image which means the object data gets repeated on several lines.
        object_id [t] : identifier of the object, must be unique in the project. It will be displayed in the object page
        object_link [f] : URL of an associated website
        object_lat [f] : latitude, decimal degrees
        object_lon [f] : longitude, decimal degrees
        object_date [f] : ISO8601 YYYYMMJJ UTC
        object_time [f] : ISO8601 HHMMSS UTC
        object_depth_min [f] : minimum depth of object, meters
        object_depth_max [f] : maximum depth of object, meters
    And, for already classified objects
        object_annotation_date [t] : ISO8601 YYYYMMJJ UTC
        object_annotation_time [t] : ISO8601 YYYYMMJJ UTC
        object_annotation_category [t] : class of the object with optionally its direct parent following separated by left angle bracket without whitespace "Cnidaria<Hydrozoa" or old style between brackets "Cnidaria (Hydrozoa)"
        object_annotation_category_id [f] : Ecotaxa ID of the class of the object, generally from an Ecotaxa export
        object_annotation_person_name [t] : name of the person who identified the object
        object_annotation_person_email [t] : email of the person who identified the object
        object_annotation_status [t] : predicted, dubious, or validated
    And additional object-related fields
        object_*** [f] or [t] : other fields relative to the object. Up to 500 [f] fields and 20 [t] ones.
    PROCESS: metadata relative to the processing of the raw images
        process_id [t] : identifier. The processing information is associated with the acquisition on the same line. If missing, a dummy processing identifier will be created.
        process_*** [t] : other fields relative to the process. Up to 30 of them.
    ACQUISITION: metadata relative to the image acquisition
        acq_id [t] : identifier of the image acquisition, must be unique in the project. If missing, a dummy acquisition identifier will be created.
        acq_instrument [t] : name of the instrument (UVP, ZOOSCAN, FLOWCAM, etc.)
        acq_*** [t] : other fields relative to the acquisition. Up to 30 of them.
    SAMPLE: a collection event
        sample_id [t] : identifier of the sample, must be unique in the project. If missing, a dummy sample identifier will be created.
        sample_*** [t] : other fields relative to the sample. Up to 30 of them.
"""


def _is_missing(v):
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if isinstance(v, numpy.floating) and numpy.isnan(v):
        return True
    return False


def _is_numeric(v):
    # bools are numbers in Python; EcoTaxa treats them as text
    if isinstance(v, bool) or isinstance(v, numpy.bool_):
        return False
    if isinstance(v, numbers.Number):
        return True
    if isinstance(v, (numpy.integer, numpy.floating)):
        return True
    return False


def _classify_column(values):
    """Return '[f]' if every non-missing value is numeric, else '[t]'."""
    has_value = False
    for v in values:
        if _is_missing(v):
            continue
        has_value = True
        if not _is_numeric(v):
            return "[t]"
    return "[f]" if has_value else "[t]"


def _format_cell(v):
    if _is_missing(v):
        return ""
    if isinstance(v, (numpy.integer, numpy.floating, numpy.bool_)):
        v = v.item()
    return str(v)


def _write_tsv(rows, out):
    """Write a 2-header EcoTaxa TSV (columns + type annotations) to a text stream."""
    # Preserve first-seen column order across all rows
    columns = []
    seen = set()
    for row in rows:
        for k in row.keys():
            if k not in seen:
                seen.add(k)
                columns.append(k)

    type_row = [_classify_column(row.get(col) for row in rows) for col in columns]

    writer = csv.writer(out, delimiter="\t", lineterminator="\n")
    writer.writerow(columns)
    writer.writerow(type_row)
    for row in rows:
        writer.writerow([_format_cell(row.get(col)) for col in columns])


def ecotaxa_export(archive_filepath, metadata, image_base_path, keep_files=False):
    """Generates the archive compatible with an export to ecotaxa

    Args:
        archive_filepath (str): path where you want the archive to be saved.
        metadata (dict): metadata regarding the files you want to export
        image_base_path (str): path where the files where saved
        keep_files (bool, optional): Whether to keep the original files or just the archive. Defaults to False (keep the archive only).
    """
    logger.info("Starting the ecotaxa archive export")
    with zipfile.ZipFile(archive_filepath, "w") as archive:
        tsv_content = []

        if "objects" in metadata:
            object_list = metadata.pop("objects")
        else:
            logger.error("No objects metadata recorded, cannot continue the export")
            return 0

        # sometimes the camera resolution is not exported as string
        if not isinstance(metadata["acq_camera_resolution"], str):
            metadata["acq_camera_resolution"] = (
                f"{metadata['acq_camera_resolution'][0]}x{metadata['acq_camera_resolution'][1]}"
            )

        for rank, roi in enumerate(object_list, start=1):
            tsv_line = {}
            tsv_line.update(metadata)
            # Array/dict metadata values (e.g. contour polygons) get JSON-encoded
            # so the TSV cell is a single deterministic string.
            for k, v in roi["metadata"].items():
                if isinstance(v, (list, dict)):
                    tsv_line["object_" + k] = json.dumps(v, separators=(",", ":"))
                else:
                    tsv_line["object_" + k] = v
            tsv_line["object_id"] = roi["name"]

            filename = roi["name"] + ".jpg"

            tsv_line.update({"img_file_name": filename, "img_rank": 1})
            tsv_content.append(tsv_line)

            image_path = os.path.join(image_base_path, filename)

            archive.write(image_path, arcname=filename)
            if not keep_files:
                os.remove(image_path)

        project = metadata.get("sample_project", "unknown_project").replace(" ", "_")
        acquisition_id = metadata.get("acq_id", "unknown_acq").replace(" ", "_")
        tsv_filename = f"Ecotaxa_{project}_{acquisition_id}.tsv"

        buf = io.StringIO()
        _write_tsv(tsv_content, buf)
        tsv_bytes = buf.getvalue().encode("utf-8")

        archive.writestr(tsv_filename, tsv_bytes)
        if keep_files:
            tsv_file = os.path.join(image_base_path, tsv_filename)
            with open(tsv_file, "wb") as f:
                f.write(tsv_bytes)
    logger.success("Ecotaxa archive is ready!")
    return 1

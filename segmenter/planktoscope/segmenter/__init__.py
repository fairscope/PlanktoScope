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

################################################################################
# Practical Libraries
################################################################################

# Logger library compatible with multiprocessing
# Library to get date and time for folder name and filename
import datetime

# Libraries manipulate json format, execute bash commands
import json

# Library for starting processes
import multiprocessing
import os

# Library to be able to sleep for a given duration
import time
from uuid import uuid4

import cv2
import numpy as np
import PIL.Image
import skimage.exposure
from scipy.stats import skew, kurtosis

################################################################################
# Other image processing Libraries
################################################################################
import skimage.measure
from loguru import logger

# Basic planktoscope libraries
import planktoscope.mqtt
import planktoscope.segmenter.ecotaxa
import planktoscope.segmenter.encoder
import planktoscope.segmenter.operations

logger.info("planktoscope.segmenter is loaded")


################################################################################
# Main Segmenter class
################################################################################
class SegmenterProcess(multiprocessing.Process):
    """This class contains the main definitions for the segmenter of the PlanktoScope"""

    @logger.catch
    def __init__(self, event, data_path):
        """Initialize the Segmenter class

        Args:
            event (multiprocessing.Event): shutdown event
        """
        super(SegmenterProcess, self).__init__(name="segmenter")

        logger.info("planktoscope.segmenter is initialising")

        self.stop_event = event
        self.__pipe = None
        self.segmenter_client = None
        # Where captured images are saved
        self.__img_path = os.path.join(data_path, "img/")
        # To save export folders
        self.__export_path = os.path.join(data_path, "export/")
        # To save objects to export
        self.__objects_root = os.path.join(data_path, "objects/")
        # To save debug masks
        self.__debug_objects_root = os.path.join(data_path, "clean/")
        self.__ecotaxa_path = os.path.join(self.__export_path, "ecotaxa")
        self.__global_metadata = None
        # path for current folder being segmented
        self.__working_path = ""
        # combination of self.__objects_root and actual sample folder name
        self.__working_obj_path = ""
        # combination of self.__ecotaxa_path and actual sample folder name
        self.__working_ecotaxa_path = ""
        # combination of self.__debug_objects_root and actual sample folder name
        self.__working_debug_path = ""
        self.__archive_fn = ""
        self.__process_id = ""
        self.__flat = None
        self.__mask_array = None
        self.__mask_to_remove = None
        self.__save_debug_img = True
        self.__process_min_ESD = 20  # microns
        # https://planktoscope.slack.com/archives/C01V5ENKG0M/p1714146253356569
        self.__remove_previous_mask = False

        # create all base path
        for path in [
            self.__ecotaxa_path,
            self.__objects_root,
            self.__debug_objects_root,
        ]:
            if not os.path.exists(path):
                # create the path!
                os.makedirs(path)

        logger.success("planktoscope.segmenter is initialised and ready to go!")

    def _find_files(self, path, extension):
        for _, _, filenames in os.walk(path, topdown=True):
            if filenames:
                filenames = sorted(filenames)
            return [fn for fn in filenames if fn.endswith(extension)]

    def _manual_median(self, images_array):
        images_array.sort(axis=0)
        return images_array[int(len(images_array) / 2)]

    def _save_image(self, image, path):
        PIL.Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).save(path)

    def _save_mask(self, mask, path):
        PIL.Image.fromarray(mask).save(path)

    def _calculate_flat(self, images_list, images_number, images_root_path):
        """Calculate a flat image from given list and images number

        Args:
            images_list (string): list of filenames to calculate a flat for
            images_number (int): image number to use, must be odd!
            images_root_path (string): path where to find the images

        Returns:
            image: median of previously sent images
        """
        # TODO make this calculation optional if a flat already exists

        # check to make sure images_number is odd
        if not images_number % 2:
            images_number -= 1

        # make sure image number is smaller than image list
        if images_number > len(images_list):
            logger.error("The image number can't be bigger than the length of the provided list!")
            images_number = len(images_list)

        logger.debug(f"Opening {images_number} images: {images_list[:images_number]}")
        # start = time.monotonic()
        # Read images and build array
        images_array = np.array(
            [
                cv2.imread(
                    os.path.join(images_root_path, images_list[i]),
                )
                for i in range(images_number)
            ]
        )

        # logger.debug(time.monotonic() - start)
        logger.success("Opening images")

        logger.info("Manual median calc")
        # start = time.monotonic()

        self.__flat = self._manual_median(images_array)
        # self.__flat = _numpy_median(images_array)

        # logger.debug(time.monotonic() - start)

        logger.success("Manual median calc")

        # cv2.imshow("flat_color", self.__flat.astype("uint8"))
        # cv2.waitKey(0)

        return self.__flat

    def _open_and_apply_flat(self, filepath, flat_ref):
        logger.info("Opening images")
        start = time.monotonic()
        # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        # Read images
        image = cv2.imread(filepath)
        # print(image)

        # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        # logger.debug(time.monotonic() - start)
        logger.success("Opening images")

        logger.info("Flat calc")
        # start = time.monotonic()
        # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

        # Correct image
        image = image / self.__flat

        # adding one black pixel top left
        image[0][0] = [0, 0, 0]

        # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        # logger.debug(time.monotonic() - start)

        image = skimage.exposure.rescale_intensity(image, in_range=(0, 1.04), out_range="uint8")
        # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        logger.debug(time.monotonic() - start)
        logger.success("Flat calc")

        # cv2.imshow("img", img.astype("uint8"))
        # cv2.waitKey(0)
        if self.__save_debug_img:
            self._save_image(
                image,
                os.path.join(self.__working_debug_path, "cleaned_image.jpg"),
            )
        return image

    def _create_mask(self, img, debug_saving_path):
        logger.info("Starting the mask creation")

        pipeline = [
            # "adaptative_threshold",
            "simple_threshold",
            "remove_previous_mask" if self.__remove_previous_mask else "no_op",
            "erode",
            "dilate",
            "close",
            "erode2",
        ]

        mask = img

        for i, transformation in enumerate(pipeline):
            function = getattr(
                planktoscope.segmenter.operations, transformation
            )  # Retrieves the actual operation
            mask = function(mask)

            # cv2.imshow(f"mask {transformation}", mask)
            # cv2.waitKey(0)
            if self.__save_debug_img:
                PIL.Image.fromarray(mask).save(
                    os.path.join(debug_saving_path, f"mask_{i}_{transformation}.jpg")
                )

        logger.success("Mask created")
        return mask

    def _get_color_info(self, bgr_img, mask):
        # bgr_mean, bgr_stddev = cv2.meanStdDev(bgr_img, mask=mask)
        # (b_channel, g_channel, r_channel) = cv2.split(bgr_img)
        # quartiles = [0, 0.05, 0.25, 0.50, 0.75, 0.95, 1]
        # b_quartiles = np.quantile(b_channel, quartiles)
        # g_quartiles = np.quantile(g_channel, quartiles)
        # r_quartiles = np.quantile(r_channel, quartiles)
        hsv_img = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2HSV)
        (h_channel, s_channel, v_channel) = cv2.split(hsv_img)
        # hsv_mean, hsv_stddev = cv2.meanStdDev(hsv_img, mask=mask)
        h_mean = np.mean(h_channel, where=mask)
        s_mean = np.mean(s_channel, where=mask)
        v_mean = np.mean(v_channel, where=mask)
        h_stddev = np.std(h_channel, where=mask)
        s_stddev = np.std(s_channel, where=mask)
        v_stddev = np.std(v_channel, where=mask)
        # Distribution skewness and kurtosis computation
        h_skewness = skew(h_channel, bias=False, axis=None)
        s_skewness = skew(s_channel, bias=False, axis=None)
        v_skewness = skew(v_channel, bias=False, axis=None)
        h_kurtosis = kurtosis(h_channel, bias=False, axis=None)
        s_kurtosis = kurtosis(s_channel, bias=False, axis=None)
        v_kurtosis = kurtosis(v_channel, bias=False, axis=None)
        
        # h_quartiles = np.quantile(h_channel, quartiles)
        # s_quartiles = np.quantile(s_channel, quartiles)
        # v_quartiles = np.quantile(v_channel, quartiles)
        return {
            # "object_MeanRedLevel": bgr_mean[2][0],
            # "object_MeanGreenLevel": bgr_mean[1][0],
            # "object_MeanBlueLevel": bgr_mean[0][0],
            # "object_StdRedLevel": bgr_stddev[2][0],
            # "object_StdGreenLevel": bgr_stddev[1][0],
            # "object_StdBlueLevel": bgr_stddev[0][0],
            # "object_minRedLevel": r_quartiles[0],
            # "object_Q05RedLevel": r_quartiles[1],
            # "object_Q25RedLevel": r_quartiles[2],
            # "object_Q50RedLevel": r_quartiles[3],
            # "object_Q75RedLevel": r_quartiles[4],
            # "object_Q95RedLevel": r_quartiles[5],
            # "object_maxRedLevel": r_quartiles[6],
            # "object_minGreenLevel": g_quartiles[0],
            # "object_Q05GreenLevel": g_quartiles[1],
            # "object_Q25GreenLevel": g_quartiles[2],
            # "object_Q50GreenLevel": g_quartiles[3],
            # "object_Q75GreenLevel": g_quartiles[4],
            # "object_Q95GreenLevel": g_quartiles[5],
            # "object_maxGreenLevel": g_quartiles[6],
            # "object_minBlueLevel": b_quartiles[0],
            # "object_Q05BlueLevel": b_quartiles[1],
            # "object_Q25BlueLevel": b_quartiles[2],
            # "object_Q50BlueLevel": b_quartiles[3],
            # "object_Q75BlueLevel": b_quartiles[4],
            # "object_Q95BlueLevel": b_quartiles[5],
            # "object_maxBlueLevel": b_quartiles[6],
            "MeanHue": h_mean,
            "MeanSaturation": s_mean,
            "MeanValue": v_mean,
            "StdHue": h_stddev,
            "StdSaturation": s_stddev,
            "StdValue": v_stddev,
            "SkewnessHue": h_skewness,
            "SkewnessSaturation": s_skewness,
            "SkewnessValue": v_skewness,
            "KurtosisHue": h_kurtosis,
            "KurtosisSaturation": s_kurtosis,
            "KurtosisValue": v_kurtosis
            # "object_minHue": h_quartiles[0],
            # "object_Q05Hue": h_quartiles[1],
            # "object_Q25Hue": h_quartiles[2],
            # "object_Q50Hue": h_quartiles[3],
            # "object_Q75Hue": h_quartiles[4],
            # "object_Q95Hue": h_quartiles[5],
            # "object_maxHue": h_quartiles[6],
            # "object_minSaturation": s_quartiles[0],
            # "object_Q05Saturation": s_quartiles[1],
            # "object_Q25Saturation": s_quartiles[2],
            # "object_Q50Saturation": s_quartiles[3],
            # "object_Q75Saturation": s_quartiles[4],
            # "object_Q95Saturation": s_quartiles[5],
            # "object_maxSaturation": s_quartiles[6],
            # "object_minValue": v_quartiles[0],
            # "object_Q05Value": v_quartiles[1],
            # "object_Q25Value": v_quartiles[2],
            # "object_Q50Value": v_quartiles[3],
            # "object_Q75Value": v_quartiles[4],
            # "object_Q95Value": v_quartiles[5],
            # "object_maxValue": v_quartiles[6],
        }

    def _extract_metadata_from_regionprop(self, prop):
        return {
            "label": prop.label,
            # width of the smallest rectangle enclosing the object
            "width": prop.bbox[3] - prop.bbox[1],
            # height of the smallest rectangle enclosing the object
            "height": prop.bbox[2] - prop.bbox[0],
            # X coordinates of the top left point of the smallest rectangle enclosing the object
            "bx": prop.bbox[1],
            # Y coordinates of the top left point of the smallest rectangle enclosing the object
            "by": prop.bbox[0],
            # circularity : (4∗π ∗Area)/Perim^2 a value of 1 indicates a perfect circle, a value approaching 0 indicates an increasingly elongated polygon
            "circ.": (4 * np.pi * prop.filled_area) / prop.perimeter**2,
            # Surface area of the object excluding holes, in square pixels (=Area*(1-(%area/100))
            "area_exc": prop.area,
            # Surface area of the object in square pixels
            "area": prop.filled_area,
            # Percentage of object’s surface area that is comprised of holes, defined as the background grey level
            "%area": 1 - (prop.area / prop.filled_area),
            # Primary axis of the best fitting ellipse for the object
            "major": prop.major_axis_length,
            # Secondary axis of the best fitting ellipse for the object
            "minor": prop.minor_axis_length,
            # Y position of the center of gravity of the object
            "y": prop.centroid[0],
            # X position of the center of gravity of the object
            "x": prop.centroid[1],
            # The area of the smallest polygon within which all points in the object fit
            "convex_area": prop.convex_area,
            # # Minimum grey value within the object (0 = black)
            # "min": prop.min_intensity,
            # # Maximum grey value within the object (255 = white)
            # "max": prop.max_intensity,
            # # Average grey value within the object ; sum of the grey values of all pixels in the object divided by the number of pixels
            # "mean": prop.mean_intensity,
            # # Integrated density. The sum of the grey values of the pixels in the object (i.e. = Area*Mean)
            # "intden": prop.filled_area * prop.mean_intensity,
            # The length of the outside boundary of the object
            "perim.": prop.perimeter,
            # major/minor
            "elongation": np.divide(prop.major_axis_length, prop.minor_axis_length),
            # max-min
            # "range": prop.max_intensity - prop.min_intensity,
            # perim/area_exc
            "perimareaexc": prop.perimeter / prop.area,
            # perim/major
            "perimmajor": prop.perimeter / prop.major_axis_length,
            # (4 ∗ π ∗ Area_exc)/perim 2
            "circex": np.divide(4 * np.pi * prop.area, prop.perimeter**2),
            # Angle between the primary axis and a line parallel to the x-axis of the image
            "angle": prop.orientation / np.pi * 180 + 90,
            # # X coordinate of the top left point of the image
            # 'xstart': data_object['raw_img']['meta']['xstart'],
            # # Y coordinate of the top left point of the image
            # 'ystart': data_object['raw_img']['meta']['ystart'],
            # Maximum feret diameter, i.e. the longest distance between any two points along the object boundary
            # 'feret': data_object['raw_img']['meta']['feret'],
            # feret/area_exc
            # 'feretareaexc': data_object['raw_img']['meta']['feret'] / property.area,
            # perim/feret
            # 'perimferet': property.perimeter / data_object['raw_img']['meta']['feret'],
            "bounding_box_area": prop.bbox_area,
            "eccentricity": prop.eccentricity,
            "equivalent_diameter": prop.equivalent_diameter,
            "euler_number": prop.euler_number,
            "extent": prop.extent,
            "local_centroid_col": prop.local_centroid[1],
            "local_centroid_row": prop.local_centroid[0],
            "solidity": prop.solidity,
        }

    def _slice_image(self, img, name, mask, start_count=0):
        """Slice a given image using give mask

        Args:
            img (img array): Image to slice
            name (string): name of the original image
            mask (mask binary array): mask to use slice with
            start_count (int, optional): count start to number the objects, so each one is unique. Defaults to 0.

        Returns:
            tuple: (Number of saved objects, original number of objects before size filtering)
        """

        def __augment_slice(dim_slice, max_dims, size=10):
            # transform tuple in list
            dim_slice = list(dim_slice)
            # dim_slice[0] is the vertical component
            # dim_slice[1] is the horizontal component
            # dim_slice[1].start,dim_slice[0].start is the top left corner
            for i in range(2):
                if dim_slice[i].start < size:
                    dim_slice[i] = slice(0, dim_slice[i].stop)
                else:
                    dim_slice[i] = slice(dim_slice[i].start - size, dim_slice[i].stop)

            # dim_slice[1].stop,dim_slice[0].stop is the bottom right corner
            for i in range(2):
                if dim_slice[i].stop + size == max_dims[i]:
                    dim_slice[i] = slice(dim_slice[i].start, max_dims[i])
                else:
                    dim_slice[i] = slice(dim_slice[i].start, dim_slice[i].stop + size)

            # transform back list in tuple
            dim_slice = tuple(dim_slice)
            return dim_slice

        labels, nlabels = skimage.measure.label(mask, return_num=True)
        regionprops = skimage.measure.regionprops(labels)
        regionprops_filtered = [
            region
            for region in regionprops
            if region.equivalent_diameter_area >= self.__process_min_ESD
        ]
        object_number = len(regionprops_filtered)
        logger.debug(f"Found {nlabels} labels, or {object_number} after size filtering")

        for i, region in enumerate(regionprops_filtered):
            region.label = i + start_count

            # Publish the object_id to via MQTT to Node-RED
            self.segmenter_client.client.publish(
                "status/segmenter/object_id",
                f'{{"object_id":"{region.label}"}}',
            )

            # First extract to get all the metadata about the image
            obj_image = img[region.slice]
            colors = self._get_color_info(obj_image, region.filled_image)
            metadata = self._extract_metadata_from_regionprop(region)

            # Calculate blur metric for this object (Laplacian variance)
            blur_laplacian = planktoscope.segmenter.operations.calculate_blur(obj_image)
            metadata["blur_laplacian"] = blur_laplacian

            # Second extract to get a bigger image for saving
            obj_image = img[__augment_slice(region.slice, labels.shape, 10)]
            object_id = f"{name}_{i}"
            object_fn = os.path.join(self.__working_obj_path, f"{object_id}.jpg")

            self._save_image(obj_image, object_fn)

            if self.__save_debug_img:
                self._save_mask(
                    region.filled_image,
                    os.path.join(self.__working_debug_path, f"obj_{i}_mask.jpg"),
                )

            object_metadata = {
                "name": f"{object_id}",
                "metadata": {**metadata, **colors},
            }

            # publish metrics about the found object
            self.segmenter_client.client.publish(
                "status/segmenter/metric",
                json.dumps(object_metadata, cls=planktoscope.segmenter.encoder.NpEncoder),
            )

            if "objects" in self.__global_metadata:
                self.__global_metadata["objects"].append(object_metadata)
            else:
                self.__global_metadata.update({"objects": [object_metadata]})

        if self.__save_debug_img:
            if object_number:
                for region in regionprops_filtered:
                    tagged_image = cv2.drawMarker(
                        img,
                        (int(region.centroid[1]), int(region.centroid[0])),
                        (0, 0, 255),
                        cv2.MARKER_CROSS,
                    )
                    tagged_image = cv2.rectangle(
                        tagged_image,
                        pt1=region.bbox[-3:-5:-1],
                        pt2=region.bbox[-1:-3:-1],
                        color=(150, 0, 200),
                        thickness=1,
                    )
                    contours, hierarchy = cv2.findContours(
                        np.uint8(region.image),
                        mode=cv2.RETR_TREE,  # RETR_FLOODFILL or RETR_EXTERNAL
                        method=cv2.CHAIN_APPROX_NONE,
                    )
                    tagged_image = cv2.drawContours(
                        tagged_image,
                        contours,
                        -1,
                        (238, 130, 238),
                        thickness=1,
                        offset=(region.bbox[1], region.bbox[0]),
                    )
                self._save_image(
                    tagged_image,
                    os.path.join(self.__working_debug_path, "tagged.jpg"),
                )
            else:
                self._save_image(
                    img,
                    os.path.join(self.__working_debug_path, "tagged.jpg"),
                )
        return (object_number, len(regionprops))

    def _pipe(self, ecotaxa_export):
        logger.info("Finding images")
        images_list = self._find_files(self.__working_path, ("JPG", "jpg", "JPEG", "jpeg"))

        logger.debug(f"Images found are {images_list}")
        images_count = len(images_list)
        if images_count == 0:
            logger.error(
                "There is no image to run the segmentation on. Please check your selection."
            )
            raise FileNotFoundError
        else:
            logger.debug(f"We found {images_count} images, good luck!")

        first_start = time.monotonic()
        self.__mask_to_remove = None
        # average = 0
        total_objects = 0
        average_objects = 0
        recalculate_flat = True
        # TODO check image list here to find if a flat exists
        # we recalculate the flat every 10 pictures
        if recalculate_flat:
            recalculate_flat = False
            self.segmenter_client.client.publish(
                "status/segmenter", '{"status":"Calculating flat"}'
            )
            if images_count < 10:
                self._calculate_flat(images_list[0:images_count], images_count, self.__working_path)
            else:
                self._calculate_flat(images_list[0:10], 10, self.__working_path)

            if self.__save_debug_img:
                self._save_image(
                    self.__flat,
                    os.path.join(self.__working_debug_path, "flat_color.jpg"),
                )

        average_time = 0

        # TODO here would be a good place to parallelize the computation
        for i, filename in enumerate(images_list):
            name = os.path.splitext(filename)[0]

            # Publish the object_id to via MQTT to Node-RED
            self.segmenter_client.client.publish(
                "status/segmenter",
                f'{{"status":"Segmenting image {filename}, image {i + 1}/{images_count}"}}',
            )

            # we recalculate the flat if the heuristics detected we should
            if recalculate_flat:  # not i % 10 and i < (images_count - 10)
                recalculate_flat = False
                if len(images_list) == 10:
                    # We are too close to the end of the list, take the previous 10 images instead of the next 10
                    flat = self._calculate_flat(images_list, 10, self.__working_path)
                elif i > (len(images_list) - 11):
                    # We are too close to the end of the list, take the previous 10 images instead of the next 10
                    flat = self._calculate_flat(images_list[i - 10 : i], 10, self.__working_path)
                else:
                    flat = self._calculate_flat(images_list[i : i + 10], 10, self.__working_path)  # noqa: F841
                if self.__save_debug_img:
                    self._save_image(
                        self.__flat,
                        os.path.join(
                            os.path.dirname(self.__working_debug_path),
                            f"flat_color_{i}.jpg",
                        ),
                    )

            self.__working_debug_path = os.path.join(
                self.__debug_objects_root,
                self.__working_path.split(self.__img_path)[1].strip(),
                name,
            )

            logger.debug(f"The debug objects path is {self.__working_debug_path}")
            # Create the debug objects path if needed
            if self.__save_debug_img:
                # create the path!
                os.makedirs(self.__working_debug_path, exist_ok=True)

            start = time.monotonic()
            logger.info(f"Starting work on {name}, image {i + 1}/{images_count}")

            img = self._open_and_apply_flat(
                os.path.join(self.__working_path, images_list[i]), self.__flat
            )

            # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            # logger.debug(time.monotonic() - start)

            # start = time.monotonic()
            # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

            mask = self._create_mask(img, self.__working_debug_path)

            # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            # logger.debug(time.monotonic() - start)

            # start = time.monotonic()
            # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

            objects_count, _ = self._slice_image(img, name, mask, total_objects)
            total_objects += objects_count
            # Simple heuristic to detect a movement of the flow cell and a change in the resulting flat
            # TODO: this heuristic should be improved or removed if deemed unnecessary
            if average_objects != 0 and objects_count > average_objects + 20:
                # FIXME: this should force a new slice of the current image
                logger.debug(
                    f"We need to recalculate a flat since we have {objects_count} new objects instead of the average of {average_objects}"
                )
                recalculate_flat = True
            average_objects = (average_objects * i + objects_count) / (i + 1)

            # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            # logger.debug(time.monotonic() - start)
            delay = time.monotonic() - start
            average_time = (average_time * i + delay) / (i + 1)
            logger.success(
                f"Work on {name} is OVER! Done in {delay}s, average time is {average_time}s, average number of objects is {average_objects}"
            )
            logger.success(
                f"We also found {objects_count} objects in this image, at a rate of {objects_count / delay} objects per second"
            )
            logger.success(f"So far we found {total_objects} objects")

        total_duration = (time.monotonic() - first_start) / 60
        logger.success(
            f"{images_count} images done in {total_duration} minutes, or an average of {average_time}s per image or {total_duration * 60 / images_count}s per image"
        )
        logger.success(
            f"We also found {total_objects} objects, or an average of {total_objects / (total_duration * 60)}objects per second"
        )

        if ecotaxa_export:
            if "objects" in self.__global_metadata:
                if planktoscope.segmenter.ecotaxa.ecotaxa_export(
                    self.__archive_fn,
                    self.__global_metadata,
                    self.__working_obj_path,
                    keep_files=True,
                ):
                    logger.success("Ecotaxa archive export completed for this folder")
                else:
                    logger.error("The ecotaxa export could not be completed")
            else:
                logger.info("There are no objects to export")
        else:
            logger.info("We are not creating the ecotaxa output archive for this folder")

        # cleanup
        # we're done free some mem
        self.__flat = None

    def segment_all(self, paths: list, force=False, ecotaxa_export=True):
        """Starts the segmentation in all the folders given recursively

        Args:
            paths (list): path list to recursively explore.
            force (bool, optional): force the rework on all paths given. Defaults to False.
            ecotaxa_export (bool, optional): generates ecotaxa export data. Defaults to True.
        """
        img_paths = []
        for path in paths:
            for x in os.walk(path):
                if x[0] not in img_paths:
                    img_paths.append(x[0])
        self.segment_list(img_paths, force, ecotaxa_export)

    def segment_list(self, path_list: list, force=False, ecotaxa_export=True):
        """Starts the segmentation in the folders given

        Args:
            paths (list): path list to recursively explore.
            force (bool, optional): force the rework on all paths given. Defaults to False.
            ecotaxa_export (bool, optional): generates ecotaxa export data. Defaults to True.
        """
        logger.info(f"The pipeline will be run in {len(path_list)} directories")
        logger.debug(f"Those are {path_list}")

        self.__process_uuid = str(uuid4())

        if self.__process_id == "":
            self.__process_id = self.__process_uuid

        logger.info(f"The process_uuid of this run is {self.__process_uuid}")
        logger.info(f"The process_id of this run is {self.__process_id}")
        exception = None

        for path in path_list:
            logger.debug(f"{path}: Checking for the presence of metadata.json")
            if os.path.exists(os.path.join(path, "metadata.json")):
                # The file exists, let's check if we force or not
                # we also need to check for the presence of done.txt in each folder
                logger.debug(f"{path}: Checking for the presence of done.txt or forcing({force})")
                if os.path.exists(os.path.join(path, "done.txt")) and not force:
                    logger.debug(f"Moving to the next folder, {path} has already been segmented")
                else:
                    # forcing, let's gooooo
                    try:
                        self.segment_path(path, ecotaxa_export)
                    except Exception as e:
                        logger.error(f"There was an error while segmenting {path}")
                        exception = e
            else:
                logger.debug(f"Moving to the next folder, {path} has no metadata.json")
        if exception is None:
            # Publish the status "Done" to via MQTT to Node-RED
            self.segmenter_client.client.publish("status/segmenter", '{"status":"Done"}')
        else:
            self.segmenter_client.client.publish(
                "status/segmenter",
                f'{{"status":"An exception was raised during the segmentation: {exception}."}}',
            )
        # Reset process_id
        self.__process_id = ""

    def segment_path(self, path, ecotaxa_export):
        """Starts the segmentation in the given path

        Args:
            path (string): path of folder to do segmentation in
        """
        logger.info(f"Loading the metadata file for {path}")
        with open(os.path.join(path, "metadata.json"), "r") as config_file:
            self.__global_metadata = json.load(config_file)
            logger.debug(f"Configuration loaded is {self.__global_metadata}")

        # Remove all the key,value pairs that don't start with acq, sample, object or process (for Ecotaxa)
        self.__global_metadata = dict(
            filter(
                lambda item: item[0].startswith(("acq", "sample", "object", "process")),
                self.__global_metadata.items(),
            )
        )

        project = self.__global_metadata["sample_project"].replace(" ", "_")
        sample = self.__global_metadata["sample_id"].replace(" ", "_")
        acquisition = self.__global_metadata["acq_id"].replace(" ", "_")
        date = datetime.datetime.utcnow().isoformat()

        self.__global_metadata["process_datetime"] = date
        self.__global_metadata["process_uuid"] = self.__process_uuid
        self.__global_metadata["process_id"] = f"{project}_{sample}_{self.__process_id}"

        # TODO Make this dynamic: if we change operations order and/or parameters, we need to make this evolve.
        self.__global_metadata["process_1st_operation"] = {
            "type": "remove_background",
            "parameters": {"type": "flat"},
        }
        self.__global_metadata["process_2nd_operation"] = {
            "type": "simple_threshold",
            "parameters": {"algorithm": "THRESH_TRIANGLE"},
        }
        self.__global_metadata["process_3rd_operation"] = {
            "type": "remove_previous_mask" if self.__remove_previous_mask else "no_op",
            "parameters": {},
        }
        self.__global_metadata["process_4th_operation"] = {
            "type": "erode",
            "parameters": {"kernel_size": 2, "kernel_shape": "rectangle"},
        }
        self.__global_metadata["process_5th_operation"] = {
            "type": "dilate",
            "parameters": {"kernel_size": 8, "kernel_shape": "ellipse"},
        }
        self.__global_metadata["process_6th_operation"] = {
            "type": "close",
            "parameters": {"kernel_size": 8, "kernel_shape": "ellipse"},
        }
        self.__global_metadata["process_7th_operation"] = {
            "type": "erode",
            "parameters": {"kernel_size": 8, "kernel_shape": "ellipse"},
        }

        # Define the name of the .zip file that will contain the images and the .tsv table for EcoTaxa
        self.__archive_fn = os.path.join(
            self.__ecotaxa_path,
            # filename includes project name, timestamp and sample id
            f"ecotaxa_{acquisition}.zip",
            # TODO #102 sanitize the filename to remove potential problems with spaces and special characters
        )

        self.__working_path = path

        # recreate the subfolder img architecture of this folder inside objects
        # when we split the working path with the base img path, we get the date/sample architecture back
        # os.path.relpath("/home/pi/data/img/2020-10-17/5/5","/home/pi/data/img/") => '2020-10-17/5/5'

        sample_path = os.path.relpath(self.__working_path, self.__img_path)

        logger.debug(f"base obj path is {self.__objects_root}")
        logger.debug(f"sample path is {sample_path}")

        self.__working_obj_path = os.path.join(self.__objects_root, sample_path)

        logger.debug(f"The working objects path is {self.__working_obj_path}")

        self.__working_debug_path = os.path.join(self.__debug_objects_root, sample_path)

        logger.debug(f"The debug objects path is {self.__working_debug_path}")

        # Create the paths
        for path in [self.__working_obj_path, self.__working_debug_path]:
            if not os.path.exists(path):
                # create the path!
                os.makedirs(path)

        logger.debug(f"The archive folder is {self.__archive_fn}")

        logger.info(f"Starting the pipeline in {path}")

        try:
            self._pipe(ecotaxa_export)
        except Exception as e:
            logger.exception(f"There was an error in the pipeline {e}")
            raise e

        # Add file 'done' to path to mark the folder as already segmented
        with open(os.path.join(self.__working_path, "done.txt"), "w") as done_file:
            done_file.writelines(datetime.datetime.utcnow().isoformat())
        logger.info(f"Pipeline has been run for {path}")

        return True

    @logger.catch
    def treat_message(self):
        last_message = {}
        if self.segmenter_client.new_message_received():
            logger.info("We received a new message")
            last_message = self.segmenter_client.msg["payload"]
            logger.debug(last_message)
            self.segmenter_client.read_message()

        if "action" in last_message:
            # If the command is "segment"
            if last_message["action"] == "segment":
                # {"action":"segment"}
                if "settings" in last_message:
                    settings = last_message["settings"]

                    # force rework of already done folder
                    force = settings.get("force", False)

                    # parse folders recursively starting from the given parameter
                    recursive = settings.get("recursive", True)

                    # generate ecotaxa output archive
                    ecotaxa_export = settings.get("ecotaxa", True)

                    # keep debug images
                    self.__save_debug_img = settings.get("keep", True)

                    if "process_id" in last_message["settings"]:
                        self.__process_id = settings["process_id"]

                    self.__process_min_ESD = settings.get("process_min_ESD", 20)

                    self.__remove_previous_mask = settings.get("remove_previous_mask", False)

                path = last_message["path"] if "path" in last_message else None

                # Publish the status "Started" to via MQTT to Node-RED
                self.segmenter_client.client.publish("status/segmenter", '{"status":"Started"}')
                if path:
                    if recursive:
                        self.segment_all(path, force, ecotaxa_export)
                    else:
                        self.segment_list(path, force, ecotaxa_export)
                else:
                    self.segment_all(self.__img_path, force, ecotaxa_export)

            elif last_message["action"] == "stop":
                logger.info("The segmentation has been interrupted.")

                # Publish the status "Interrupted" to via MQTT to Node-RED
                self.segmenter_client.client.publish("status/segmenter", '{"status":"Interrupted"}')

            elif last_message["action"] == "update_config":
                logger.error("We can't update the configuration while we are segmenting.")

                # Publish the status "Interrupted" to via MQTT to Node-RED
                self.segmenter_client.client.publish("status/segmenter", '{"status":"Busy"}')

            elif last_message["action"] != "":
                logger.warning(f"We did not understand the received request {last_message}")

    ################################################################################
    # While loop for capturing commands from Node-RED
    ################################################################################
    @logger.catch
    def run(self):
        """This is the function that needs to be started to create a thread"""
        logger.info(f"The segmenter control thread has been started in process {os.getpid()}")

        # MQTT Service connection
        self.segmenter_client = planktoscope.mqtt.MQTT_Client(
            topic="segmenter/#", name="segmenter_client"
        )

        # Publish the status "Ready" to via MQTT to Node-RED
        self.segmenter_client.client.publish("status/segmenter", '{"status":"Ready"}')

        logger.success("Segmenter is READY!")

        # This is the loop
        while not self.stop_event.is_set():
            self.treat_message()
            time.sleep(0.5)

        logger.info("Shutting down the segmenter process")
        self.segmenter_client.client.publish("status/segmenter", '{"status":"Dead"}')
        self.segmenter_client.shutdown()
        logger.success("Segmenter process shut down! See you!")


# This is called if this script is launched directly
if __name__ == "__main__":
    # TODO This should be a test suite for this library
    pass

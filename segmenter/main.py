# Copyright Romain Bazile and other PlanktoScope project contributors
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
import multiprocessing
import os
import signal  # for handling SIGINT/SIGTERM
import time

from loguru import logger

import planktoscope.segmenter

logger.info("Starting the PlanktoScope data processing segmenter!")

run = True  # global variable to enable clean shutdown from stop signals

data_path = os.getenv(
    "PLANKTOSCOPE_DATA_PATH", os.path.normpath(os.path.join(os.path.dirname(__file__), "../data"))
)


def handler_stop_signals(signum, _):
    """This handler simply stop the forever running loop in __main__"""
    global run
    logger.info(f"Received a signal asking to stop {signum}")
    run = False


if __name__ == "__main__":
    logger.info("Welcome!")
    logger.info(f"Using data_path {data_path}")
    logger.info("Initialising signals handling and sanitizing the directories (step 1/2)")
    signal.signal(signal.SIGINT, handler_stop_signals)
    signal.signal(signal.SIGTERM, handler_stop_signals)

    export_path = os.path.join(data_path, "export/ecotaxa")

    # create the path!
    os.makedirs(export_path, exist_ok=True)

    # Prepare the event for a graceful shutdown
    shutdown_event = multiprocessing.Event()
    shutdown_event.clear()

    # Starts the segmenter process
    logger.info("Starting the segmenter control process (step 2/2)")
    try:
        segmenter_thread = planktoscope.segmenter.SegmenterProcess(shutdown_event, data_path)
    except Exception:
        logger.error("The segmenter control process could not be started")
        segmenter_thread = None
    else:
        segmenter_thread.start()

    logger.success("Looks like the segmenter is set up and running, have fun!")

    while run:
        if not segmenter_thread or not segmenter_thread.is_alive():
            logger.error("The segmenter process died unexpectedly! Oh no!")
            break
        time.sleep(1)

    logger.info("Shutting down...")
    shutdown_event.set()
    time.sleep(1)

    if segmenter_thread:
        segmenter_thread.join()

    if segmenter_thread:
        segmenter_thread.close()

    logger.info("Bye!")

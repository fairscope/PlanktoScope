---
name: Test Suite Run
about: Run the test suite to help us
title: "Test Suite Run"
labels: test-run
assignees: ""
---

# Info

**PlanktoScope**

- Hardware version: eg `v2.6` or `v3.0`
- Software version: eg `2026.0.0-beta.1`
- Machine name: eg `sponge-bob`
- Serial number: eg `U132` (leave empty if unknown)

**Computer**

- Operating system: eg `macOS 14.1`
- Browser: eg `Firefox 128`

**Comment**

Anything else worth knowing?

# Test suite

Start or restart the PlanktoScope

Prepare tubing, sample and flowcell.

## Display

* [ ] The PlanktoScope shows its name on the epaper (v3 only)

## Network

Replace `{machine-name}` with your PlanktoScope name.

### Direct Ethernet

1. Connect the USB <-> RJ45 cable (USB on your computer, RJ45 on the PlanktoScope)
2. Enable [connection sharing](https://fairscope.com/ics) on your computer
3. [ ] The PlanktoScope displays an IP address different than `192.168.4.1` (v3 only)
4. [ ] PlanktoScope is accessible at [http://<ip-address>/](http://<ip-address>/)
5. [ ] The preview works correctly

### Direct WiFi

1. [ ] The WiFi network "PlanktoScope {machine-name}" is visible
2. [ ] The PlanktoScope displays IP address `192.168.4.1` (v3 only)
3. [ ] You can connect your computer to the PlanktoScope WiFi hotspot
4. PlanktoScope preview is functional at
   1. [ ] [http://planktoscope.local](http://planktoscope.local)
   2. [ ] [http://192.168.4.1/](http://192.168.4.1/)
   3. [ ] [http://planktoscope-{machine-name}.local/](http://planktoscope-{machine-name}.local/)

### LAN Ethernet

1. Connect the PlanktoScope to your router ethernet
2. [ ] The PlanktoScope displays an IP address different than `192.168.4.1` (v3 only)
3. [ ] PlanktoScope preview is functional at
  1. [ ] [http://<ip-address>/](http://<ip-address>/)
  2. [ ] [http://planktoscope-{machine-name}.local](http://planktoscope-{machine-name}.local)

## Preview

Go to preview

**Light**

1. [ ] Light "On" turns on the LED
2. [ ] Light "Off" turns off the LED

**Focus**

1. [ ] "10000 μm" + "Near" moves the stage towards the camera
2. [ ] "10000 μm" + "Far" moves the stage away from the camera
3. [ ] "Stop" stops movement

**Pump**

1. [ ] "Backward" pumps anticlockwise
2. [ ] "Forward" pumps clockwise
3. [ ] "Flowrate" impacts "Backward" speed
4. [ ] "Flowrate" impacts "Forward" speed
5. [ ] "Volume" impacts "Backward" duration
6. [ ] "Volume" impacts "Forward" duration
7. [ ] "Stop" stops the pump

**Bubbler** (v3 only)

1. Connect tube, needle and plunge in a glass of water
2. [ ] `25%` generates slow bubbles
3. [ ] `50%` generates bubbles faster than `25%`
4. [ ] `75%` generates bubbles faster than `55%`
4. [ ] `100%` generates bubbles faster than `75%`
5. [ ] `Off` stops the bubbler

**Calibration**

1. [ ] Calibrate opens the Camera Calibration popup
2. [ ] The "Calibrate" button performs a successful calibration

<!-- TODO: Consider how to verify the calibration is correct -->

**Camera**

1. [ ] Move an object such as your finger in front of the camera
2. [ ] The preview streams the video without significant lag
3. [ ] Test zoom in and zoom out
4. [ ] Capture button opens a snapshot of the preview on your computer

## Metadata

Go to Metadata

**Sampling Gear**

1. [ ] "Horizontal Net" enables "Ending point"
Net Specificity
2. [ ] "Horizontal Net" enables "Net Specificity"
2. [ ] "Horizontal Net" enables "Sample information"



2. [ ] "Vertical Net" disables "Ending point"
3. [ ] "Vertical Net" enables "Net Specificity"
2. [ ] "Vertical Net" enables "Sample information"


3. [ ] "Niskin bottle" disables "Ending point"
3. [ ] "Niskin bottle" disables "Net Specificity"
2. [ ] "Niskin bottle" enables "Sample information"

4. [ ] "Lab culture" disables "Ending point"
3. [ ] "Lab culture" disables "Net Specificity"
3. [ ] "Lab culture" disables "Net Specificity"

5. [ ] "Demo / Test" disables "Ending point"
3. [ ] "Demo / Test" disables "Net Specificity"
3. [ ] "Demo / Test" disables "Net Specificity"


Note: "Sample Comment" field is alaways enabled.

<!-- TODO: format -->

**Starting point**

1. [ ] Updating Latitude moves the marker on the map
2. [ ] Updating Longitude moves the marker on the map

**Ending point**

1. [ ] Updating Latitude moves the marker on the map
2. [ ] Updating Longitude moves the marker on the map

## Acquisition

0. [ ] The green banner shows correct and previously selected metadata
1. [ ] Selecting "High Mag (100µm)" launch calibration and shows "magnification: high" on preview
2. [ ] Selecting "Medium Mag (300µm)" launch calibration and shows "magnification: medium" on preview
3. [ ] Selecting "Low Mag (500µm)" launch calibration and shows "magnification: low" on preview
4. [ ] Start an acquisition of 10 img
5. [ ] Pump rotatates between each img
6. [ ] Button "Pause" is functional
7. [ ] Button "Resume Acquisition" is functional
8. [ ] Button "Stop" is functional

## Segmentation

0. [ ] Go to "Segmentation"
1. [ ] The last acquisition appears in the table
2. [ ] The column values are correct
3. [ ] The Gallery button opens a new tab with the `jpg` files
4. [ ] Verify the content of `metadata.json`
5. [ ] Click on the "Segment" button
6. [ ] A popup appears with the correct metadata
7. [ ] Confirm "Segment"
8. [ ] The segmentation is correct
9. [ ] Deleting the acquisition from the table is functional

## Validation

0. [ ] Go to "Validation"
1. [ ] The last segmentation appears in the table
2. [ ] The colum values are correct
3. [ ] Press the "Open" button
4. [ ] "Metadata" section is correct
5. [ ] "Quality Control" section is functional
6. [ ] "Gallery" section shows the image of segmented objects
7. [ ] Click on a segmented object image
8. [ ] The popup information are correct
9. [ ] Deleting the segmentation from the table is functional
10. [ ] The ecotaxa export is functional and correct
11. [ ] In the Gallery section, test
  1. [ ] Image Zoom
  2. [ ] Filter by ID
  3. [ ] Sort by metric


## Ecotaxa

1. Go to Ecotaxa
2. Import the zip and wait for completion
3. [ ] The result on Ecotaxa matches expectations

## Administration

1. [ ] "Reboot" button is working
2. [ ] "Shutdown" button is working

## Additional tests

If you've run tests that are not included in this test suite, please describe them here and share results.

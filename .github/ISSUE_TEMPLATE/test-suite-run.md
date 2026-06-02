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

(re) start the PlanktoScope

<!--## Sample

1. Go to "Sample"
2. Select "Plankton net" for Sample gear
3. Fill the form
4. [ ] The calculations are correct-->

<!-- TODO: Add a tool to verify calculations -->

## Optic

**LED and preview**

1. [ ] Light "On" turns on the LED
2. [ ] The preview shows images without significant lag
3. [ ] The "Calibrate" button performs a successful calibration
4. [ ] Light "Off" turns off the LED

**Focus**

1. [ ] "500 μm" + "Near" moves the stage towards the camera
2. [ ] "500 μm" + "Far" moves the stage away from the camera
3. [ ] "Stop" stops movement

**Pump**

1. [ ] "Backward" pumps in the direction of the camera
2. [ ] "Forward" pumps in the opposite direction of the camera
3. [ ] "Flowrate" impacts "Backward" speed
4. [ ] "Flowrate" impacts "Forward" speed
5. [ ] "Volume" impacts "Backward" duration
6. [ ] "Volume" impacts "Forward" duration
7. [ ] "Stop" stops the pump

**Bubbler**

1. Connect tube, needle and plunge in a glass of water
2. [ ] `25%` generates slow bubbles
3. [ ] `50%` generates bubbles faster than `25%`
4. [ ] `75%` generates bubbles faster than `55%`
4. [ ] `100%` generates bubbles faster than `75%`
5. [ ] `Off` stops the bubbler

**Prepare**

Prepare tubing, sample and flowcell.

Setup focus in "Optic Configuration"

## Fluidic acquisition

**UI**

1. [ ] "Number of images to acquire" and "Pumped volume" correctly updates "Total imaged volume" and "Total pumped volume"
2. [ ] Delay to stabilize image cannot be lower than 0.1
3. [ ] Delay to stabilize image cannot be higher than 5
4. [ ] "Flowcell" offers 5 different options
5. [ ] "Statistics" is coherent with information entered in "Sample"

**Small capture**

1. Start acquisition with 5 images
2. [ ] "Capture progress" shows progress
3. Wait for completion
4. Go to "Gallery" in the menu
5. [ ] Go to `img` -> `<today's date>` -> `name of the sample` -> `name of the acquisition`
6. [ ] There are 5 jpeg images of acceptable quality
7. [ ] There is a `metadata.json` file with coherent information
8. [ ] There is an `integrity.check` file listing the 5 images and the `metadata.json` file
9. Open one of the image and click the "HD" button
10. The quality is acceptable and the focus is correct

**Big capture**

1. Start acquisition with 100 images

## Segmentation

1. Start segmentation
2. [ ] "Status" updates and shows progress
3. Wait for segmentation to complete
4. Note the number of object counts
5. Go to "Gallery" in the menu
6. [ ] Go to `objects` -> `<today's date>` -> `name of the sample` -> `name of the acquisition`
7. [ ] There are as many jpeg images as there were objects counted
8. [ ] The jpeg images are of acceptable quality9.
9. [ ] There is a `ecotaxa_<name of the acquisition>.tsv` file
10. Open one of the image and click the "HD" button
11. The quality is acceptable and the focus is correct

## Ecotaxa

1. Go to "Gallery" in the menu
2. [ ] Go to `export` -> `ecotaxa`
3. [ ] Download the `ecotaxa_<name of the acquisition>.zip` file
4. Go to Ecotaxa
5. Import the zip and wait for completion
6. [ ] The result on Ecotaxa matches expectations

## Administration

1. [ ] "Reboot" button is working
2. [ ] "Shutdown" button is working

## Network

Replace `{machine-name}` with your PlanktoScope name.

### Direct Ethernet

1. Connect the USB <-> RJ45 cable (USB on your computer, RJ45 on the PlanktoScope)
2. Enable connection sharing on your computer
3. [ ] The PlanktoScope displays an IP address different than `192.168.4.1` (v3 only)
4. [ ] PlanktoScope is accessible at [http://<ip-address>/](http://<ip-address>/)
5. [ ] The preview works correctly

### Direct WiFi

1. [ ] The WiFi network "PlanktoScope {machine-name}" is visible
2. [ ] You can connect your computer to the PlanktoScope WiFi hotspot
2. PlanktoScope is accessible at
   1. [ ] [http://planktoscope.local](http://planktoscope.local)
   2. [ ] [http://192.168.4.1/](http://192.168.4.1/)
   3. [ ] [http://planktoscope-{machine-name}.local/](http://planktoscope-{machine-name}.local/)

### LAN Ethernet

1. Connect the PlanktoScope to your router ethernet
2. [ ] The PlanktoScope displays an IP address different than `192.168.4.1` (v3 only)
3. [ ] PlanktoScope is accessible at [http://<ip-address>/](http://<ip-address>/)
4. [ ] Preview works correctly
5. [ ] PlanktoScope is accessible at [http://planktoscope-{machine-name}.local](http://planktoscope-{machine-name}.local)
6. [ ] Preview works correctly

## Additional tests

If you've run tests that are not included in this test suite, please describe them here and share results.

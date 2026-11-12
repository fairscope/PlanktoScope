# Camera Settings

This document explains how the PlanktoScope software controls the PlanktoScope's camera using the camera settings exposed by the "Optic Configuration" page of the PlanktoScope's Node-RED dashboard.

The following camera settings can be adjusted via the Node-RED dashboard:

- "ISO" & "Shutter Speed" control the brightness of images captured by the camera.

- "Auto White Balance", "WB: Red", and "WB: Blue" control the color balance of images captured by the camera.

## Image brightness

### "Shutter Speed" (actually exposure time)

The Node-RED dashboard's "Shutter Speed" setting, which is specified in units of microseconds (μs), is used to set the `ExposureTime` control with the [picamera2 library](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf#page=76&zoom=100,153,0); a higher value for this setting will make captured images brighter and - when objects are moving - blurrier. To prevent the camera from capturing blurry images of moving objects, the value of this setting should be minimized; usually the default value of 125 μs is appropriate. For a detailed explanation of the exposure time of the camera sensor, refer to the [picamera library's discussion of "exposure time"](https://picamera.readthedocs.io/en/release-1.13/fov.html#exposure-time).

### "ISO" (actually sensor gain)

The Node-RED dashboard's "ISO" setting is multiplied by a camera-dependent conversion factor (0.0184 for the Pi Camera v2 Module found in PlanktoScope hardware v2.1; and 0.023125 for the Pi HQ Camera Module found in PlanktoScope hardware v2.5 and subsequent hardware versions); the result is used to set the `AnalogueGain` control with the picamera2 library. A higher value for this setting will make the camera sensor more sensitive to light, and thus make captured images brighter and noisier. To prevent the camera from capturing excessively dark images - which will prevent the PlanktoScope's segmenter from correctly detecting objects - the value of this setting should not be too low. To prevent the camera from "washing out" images by making everything excessively bright - which will destroy visual detail in the images - the value of this setting should not be too high, either. For a detailed explanation of the analog gain of the camera sensor, refer to the [picamera library's discussion of "sensor gain"](https://picamera.readthedocs.io/en/release-1.13/fov.html#sensor-gain) and the [picamera2 library](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf#page=76&zoom=100,153,0)'s discussion of the `AnalogueGain` control and the `DigitalGain` property.

## Image color balance

The PlanktoScope's camera can operate with "Automatic White Balance" mode either enabled or disabled. In ["Automatic White Balance" mode](https://datasheets.raspberrypi.com/camera/raspberry-pi-camera-guide.pdf#page=31&zoom=100,96,501), the camera ignores any manually-set white-balance settings and instead applies an adaptive algorithm to automatically (and gradually) correct the color balance of the images to prevent them from appearing more red or more blue than we would expect the images to be. However, "Automatic White Balance" mode prevents images from having consistent calibrations, so we recommend always disabling "Automatic White Balance" mode when collecting data with the PlanktoScope, and instead manually calibrating the camera's white-balance settings.

The camera's manual white-balance settings consist of two normalized color values, which are the *red gain* ("WB: Red" in the Node-RED dashboard) and the *blue gain* ("WB: Blue" in the Node-RED dashboard). The red gain can be understood as a multiplier applied to the image to achieve the desired ratio between the redness of the image and the greenness of the image, so a higher value will make the image appear redder. Similarly, the blue gain can be understood as a multiplier applied to the image to achieve the desired ratio between the blueness of the image and the greenness of the image, so a higher value will make the image appear bluer. For a deeper conceptual explanation of white balance, refer to the first two pages of Freescale Semiconductor's application note on [white balance and color correction in digital cameras](https://web.archive.org/web/20230401000000/https://www.nxp.com/docs/en/application-note/AN1904.pdf).

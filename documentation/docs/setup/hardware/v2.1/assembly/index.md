# Assembly guide of the PlanktoScope
![Complete](images/pictures/complete.webp)

You can also use CAD renders from the following link as a supplementary material for this assembly guide:

- [CAD renders for the assembly guide](https://docs.google.com/presentation/d/13zDOGUVqgMvG0O11IOMVPIQBnWrfpkxs6CpLTylAv8o/present?slide=id.g8352987986_0_674)

For the assembly guide below, the pieces of the laser-cut structure are referred to by single-letter labels (A, J, L, K, H, F, E, C, B, N, M, D, G, I) according to the following assignments:

![laser-cut part labels](images/laser-cut-part-labels.jpg)

## Step 1: Gather everything you need

For the full list of all required tools and parts, please refer to the [v2.1 hardware kit production guide](../kit/index.md).

- Laser cut structure
- M12 lenses
- Peristaltic pump and tubing
- Raspberry Pi, motor driver board, GPIO connectors
- Flashed SD card
- Stepper motors
- PiCam and flex cable
- GPIO ribbon connector, headers, HATs, LED
- DC Power terminal
- Magnets
- Super glue
- Standoffs (M2.5), M3 screws and nuts

Make sure you have your screwdriver kit, soldering iron, and components ready. Also, remember to flash the PlanktoScope image disk on the SD card before installing the Raspberry Pi.

If you are not familiar with any process, such as soldering, tapping, or wiring, try and familiarize yourself with the topics first.

Soldering deals with high heat and potentially toxic materials, so make sure to use the proper precautions.

## Step 2: Standoff installation
![step-2](images/pictures/step-2.webp)
![step-2 standoff location](images/render/step-2.webp)

Place 8 standoffs (M2.5 6mm) into the designated holes on the laser-cut base A. A pair of pliers make the job more comfortable. Do not overtighten as it is possible to crack the base material.

![step-3](images/pictures/step-3.webp)

## Step 3: Motor HAT preparation
![step-4](images/pictures/step-4.webp)

Insert and solder the terminal blocks and headers onto the motor driver PCB. 

![step-5](images/pictures/step-5.webp)

Place the motor driver PCB on to the indicated standoffs.

## Step 4: Magnets setup
![step-6](images/pictures/step-6.webp)

Now is a good time to think about how the magnets will function within the microscope. The magnets in the sample stage will need to attract to the magnets on the flow cell holder. The magnets in the objective holder will need to attract the magnets on the mount. Keep this in mind as you are adding your magnets and tapping your respective M12 holders so your orientation will be correct.

![step-8](images/pictures/step-8.webp)

You can now fix your magnets into their appropriate holes on sample stage **B**.
It is recommended to glue the magnets in place. If the magnets are too large to fit in, the holes can be widened with a handheld drill. However, they should be quite snug in place. Before you glue them in place make sure that the polarity is maintained, as they will be impossible to remove after gluing.

## Step 5: Sample stage assembly
![step-9](images/pictures/step-9.webp)

Don’t be alarmed by the color swap, this is the sample stage **B**. You can now fit the pegs on the driver mounts into the corresponding holes on the sample stage. They should be glued in place with superglue or epoxy. You can spin the shaft to align the driver mounts on the 2 steppers if it helps making the process easier.

![step-10](images/pictures/step-10.webp)

You should now have a sample stage and motor assembly that looks like this.

## Step 6: Lenses tapping and mounting
![step-12](images/pictures/step-12.webp)

You now need to tap the holes for the M12 lenses in stage and mount **M** and **D**. It is helpful for alignment to do both the objective and tube lens mount together. It is important to do this as straight as possible. A drop of mineral or olive oil can help the process. Be careful to use a right-hand tap (that goes down when turning clockwise).

![step-13](images/pictures/step-13.webp)
![step-14](images/pictures/step-14.webp)

![step-6-2](images/render/step-6-2.webp)

You can now screw the objective lens (the 25mm one) in part **D**.
![step-14](images/pictures/step-15.webp)

## Step 7: Camera preparation
You can now unscrew the lens from the Pi camera, being careful not to disturb the sensor below.
![image-22](images/pictures/image-22.webp)
![image-30](images/pictures/image-30.webp)

## Step 8: Camera mount
![step-17](images/pictures/step-17.webp)

You can mount the camera using the appropriate holes on the camera mount **G**. Be careful to avoid getting oil or dust on the sensor.

## Step 9: LED preparation
![step-18](images/pictures/step-18.webp)

The LED can then be wired up and put into its mount **F**. If you wire the LED yourself, remember to give enough length to reach the motor driver on the other end of the microscope. You can also add a bit of glue to fix **F** to the motor mount **E** at this time to make assembly easier, though it is not required.

!!! warning
    ![Led](images/render/led.webp)

    This picture shows the correct wiring for the LED. Please make sure the red wire is on the long pin of the LED.


## Step 10: Vertical slices assembly
You can now start placing the motor mount/LED assembly- **B**,
![step-5](images/render/step-5.webp)

**C**,
![step-6](images/render/step-6.webp)

**D**,
![step-7](images/render/step-7.webp)

**E**,
![step-8](images/render/step-8.webp)

**F**,
![step-8](images/render/step-9.webp)

and **G** into the base **A**.

## Step 11: Pump setup
The pump can then be mounted in place on **H**. Thread the wires through the hole with the pump tubing pointed toward the holes on the mount.
![step-19](images/pictures/step-19.webp)

Fix the pump in place.
![step-20](images/pictures/step-20.webp)

## Step 12: Pump mounting
You can now mount the pump on base **A**.
![step-15](images/render/step-15.webp)

Your setup should look like this. Don't worry about the wiring, we'll have a look at it in the next step!

![step-21](images/pictures/step-21.webp)

## Step 13: Motor HAT wiring
![step-22](images/pictures/step-22.svg)

You will now want to wire the steppers and pump to the terminals on the motor driver board.

!!! info
    The PlanktoScope **uses only bipolar stepper motors** (with 4 wires coming out, and two coils inside), so you need to identify the two wires working together for each coil. The [RepRap Wiki has great information](https://reprap.org/wiki/Stepper_wiring#.22pair.22_wires_on_4_wire_motors) on how to do this, either with a multimeter or without.
    
    You can find more information about stepper motors and how they work in this [RepRap Wiki page about stepper motors](https://reprap.org/wiki/Stepper_motor).


!!! tip
    If your wires are too short, you can invert the pump and the focus wiring. However, you will have to remember to change the configuration later on.

!!! tip
    Make sure the wires are properly connected by pulling on them a little. They should not come loose.

## Step 14: Raspberry Pi setup and installation
![step-24](images/pictures/step-24.webp)

At this point, you can insert your flashed SD card into your Raspberry Pi. If you did not already flash your SD card with the PlanktoScope OS, [refer to our guide for doing so](../../../software/standard-install.md). The heat sink can also be added to the processor.

![step-16](images/render/step-16.webp)

Mount the Raspberry Pi containing the flashed SD card on the standoffs attached to the laser cut base A.

## Step 15: Standoffs
![step-17](images/render/step-17.webp)

Add 8 standoffs (M2.5 15mm) to fix the motor driver board and the Raspberry Pi to the base. 

![step-25](images/pictures/step-25.webp)

## Step 16: Camera flex cable
![step-26](images/pictures/step-26.webp)

At this point you can use the Pi camera flex cable to connect the camera to the Pi. This is done by gently pulling up the tensioners, inserting the cable in the right orientation, then pushing the tensioners back in place to set the cable. Try not to kink or fold the flex cable too much as it is possible to damage it.

## Step 17: Power supply wiring
![step-29](images/pictures/step-29.webp)

The power wires can be wired into place on the motor driver board.

!!! tip
    Make sure the wires are properly connected by pulling on them a little. They should not come loose.

## Step 18: Prepare the GPS HAT

!!! tip
    If you don't have a GPS HAT, you can just skip the assembly steps related to the GPS HAT - the PlanktoScope software will still work without GPS.

![step-18-1](images/render/step-18-1.webp)

Insert the battery to power the GPS HAT and solder the terminal mounts in place.

## Step 19: Install the GPS HAT
![step-18](images/render/step-18.webp)

Mount the GPS HAT over the motor driver PCB using the standoffs attached to the laser cut base **A**.

## Step 20: Install the Fan HAT
![step-19](images/render/step-19.webp)

Place the cooling fan HAT above the Raspberry Pi by mounting it to the standoffs on base **A**.

!!! warning
    Be careful to slide the camera flat cable in the slot in the HAT above the connector.

## Step 21: Secure the HATS
![step-20](images/render/step-20.webp)

Secure the cooling fan HAT and GPS HAT by tightening the 8 screws to the standoffs on base A

## Step 22: Install back panel
![step-21](images/render/step-21.webp)

Insert the laser cut border **I** into base **A**.

## Step 23: GPS output connector
![step-22](images/render/step-22.webp)

Insert the power and GPS connectors into side plate **J**.

## Step 24: Install side panel
![step-23](images/render/step-23.webp)

Place the side plate **J** into the designated slots on the base. You can connect the GPS cable to its connector on the board.

!!! warning
    The GPS connector is quite fragile, make sure to align it properly before inserting it.

## Step 25: Install the other side panel
![step-25](images/render/step-25.webp)

Mount the side plate **K** on base **A** using the assigned slots.

## Step 26: Secure the sides together
![step-26](images/render/step-26.webp)

Secure the laser cut sides with the screws and nuts.

## Step 27: Secure the sides to the base plate
![step-27](images/render/step-27.webp)

Secure the laser cut sides to the base plate **A** with the screws and nuts.

!!! warning
    To make this easier, you can turn the assembly upside down or on its side. Be careful when doing so as the plates may fall.

## Step 28: Insert the camera ribbon cable in the camera
![step-28](images/pictures/step-28.webp)

You can now connect the camera flex cable into the connector on the camera board. Once again, gently pull up the tensioners, insert the cable in the right orientation, and push the tensioners back in place to set the cable. Try not to kink or fold the flex cable too much as it is possible to damage it.

## Step 29: Assemble the GPIO ribbon cable
If you didn't get an already assembled ribbon cable, you need to build it yourself.

The orientation of the connector does not really matter. However, you need to make sure that both connectors are oriented in the same direction and are on the same side of the ribbon.

To assemble, slide the ribbon in its connector and close it off. You need to tighten it really hard. It's very warmly recommended to use a vice to do so.

!!! warning
    Once assembled, the ribbon should NOT look like this:
    ![Ribbon wrong](images/pictures/ribbon_wrong.webp)

    It should rather look like this:
    ![Ribbon good](images/pictures/ribbon_good.webp)


## Step 30: Insert the ribbon cable
![step-28](images/render/step-28.webp)

Attach the GPIO ribbon to connect the cooling fan HAT to the GPS HAT.

!!! tip
    You can try to route the flat ribbon from the camera under the ribbon cable you are connecting now.
    ![step-31](images/pictures/step-31.webp)

## Step 31: Fluidic assembly
![step-29](images/render/step-29.webp)

Feed in the tubing from syringe 1 to form the fluidic path as shown.

![step-30](images/render/step-30.webp)

Feed in the tubing from syringe 2 to form the fluidic path as shown

![step-31](images/render/step-31.webp)

Feed in a length of tubing as shown through motor mount **H** and illumination mount **FE**

![step-34](images/pictures/step-34.webp)

## Step 32: Close your PlanktoScope

!!! warning
    Take a moment to check your wiring one last time. Also check the routing, make sure the LED wires and the pump stepper wires are in their dedicated channel.

![step-33](images/render/step-33.webp)

Place the top **L** into the slots on the PlanktoScope body. Secure it in place with screws and nuts.

![step-34](images/render/step-34.webp)

## Step 33: Enjoy!

Congratulations on a job well done. You can have some rest, get a tea and some biscuits!

![step-35](images/render/step-35.webp)

!!! warning
    If this was your first time assembling a PlanktoScope, you will probably need to do some troubleshooting of problems with the hardware assembly before your PlanktoScope will fully work. Refer to our [troubleshooting documentation](../../../../troubleshooting/index.md) for assistance.

## Next steps

Once your PlanktoScope fully works, you can proceed to our [operation guide](../../../../operation/index.md) to learn how to operate your PlanktoScope.

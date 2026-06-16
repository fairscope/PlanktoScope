# Creating a new update

Since PlanktoScope OS v2026, we use [RAUC](https://rauc.readthedocs.io/) to create and install software updates.

The PlanktoScope contains 2 slots; A and B; each able to host the entirety of the operating system.

To create an update

* Boot the PlanktoScope to slot A
* Install RPIOS to slot B
* Boot the PlanktoScope to slot B
* Run the setup script
* Run the postinstall script
* Run the preimage script
* Boot the PlanktoScope to slot A
* Create bundle

A and B also work the other way around.

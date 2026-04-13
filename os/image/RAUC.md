```sh
openssl req -x509 -newkey rsa:4096 -nodes -keyout demo.key.pem -out demo.cert.pem -subj "/O=rauc Inc./CN=rauc-demo"


sudo dd if=/dev/nvme0n1p3 of=firmwarefs.vfat.img bs=64M status=progress
sudo dd if=/dev/nvme0n1p5 of=rootfs.ext4.img bs=64M status=progress
rauc --cert demo.cert.pem --key demo.key.pem bundle temp-dir/ update-2015.04-1.raucb

sudo rauc service --conf system.conf
# sudo rauc service --override-boot-slot=A --conf system.conf
# Without --override-boot-slot=A - it properly detects without custom bootloader
# on first run only - maybe the boot slot is stored somewhere?

rauc install update-2015.04-1.raucb
```

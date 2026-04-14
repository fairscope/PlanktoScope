```sh
openssl req -x509 -newkey rsa:4096 -nodes -keyout demo.key.pem -out demo.cert.pem -subj "/O=rauc Inc./CN=rauc-demo"


sudo dd if=/dev/nvme0n1p3 of=temp-dir/firmware.vfat.img bs=64M status=progress
sudo dd if=/dev/nvme0n1p5 of=temp-dir/root.ext4.img bs=64M status=progress
sudo rauc --cert demo.cert.pem --key demo.key.pem bundle temp-dir/ update-2015.04-1.raucb

sudo rauc service --conf system.conf
# it knows which slot booted by reading cmdline on first run
# rauc-event-Message: 10:09:25.769: Booted into root.1 ()
# but you can override with
# sudo rauc service --override-boot-slot=A --conf system.conf

rauc install update-2015.04-1.raucb
```

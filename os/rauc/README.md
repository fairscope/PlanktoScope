```sh
openssl req -x509 -newkey rsa:4096 -nodes -keyout demo.key.pem -out demo.cert.pem -subj "/O=rauc Inc./CN=rauc-demo"



# TODO: move to /etc/rauc/system.conf (yes on both partitions)
sudo rauc service --conf system.conf
# it knows which slot booted by reading cmdline on first run
# rauc-event-Message: 10:09:25.769: Booted into root.1 ()
# but you can override with
# sudo rauc service --override-boot-slot=A --conf system.conf

rauc install update-2015.04-1.raucb
```

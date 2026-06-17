# RAUC

[RAUC](https://rauc.readthedocs.io/en/latest/) is the software we use to handle software updates on the PlanktoScope.

We have an A/B partitioning setup see [os/image](../image) for which RAUC is aware of.

## Install a bundle

```sh
rauc install PlanktoScope-update-xxx-xx-xx.raucb
```

This will install the update on the slot that is not the booted one. See `rauc status`.

## Signing

We are using the simplest possible form/method of bundle signing. Efforts to improve security is tracked [here](https://github.com/fairscope/PlanktoScope/issues/811).

The certificate/key was created with:

```sh
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout planktoscope-rauc-key.pem \
  -out planktoscope-rauc-cert.pem \
  -days 7305 \
  -subj "/C=FR/O=PlanktoScope/CN=PlanktoScope RAUC"
sudo cp planktoscope-rauc-cert.pem /etc/rauc/cert.pem
```

import { $ } from "execa"

import { getPartitions } from "../image/planktoscope.js"

async function createBundle(device, bootname) {
  const partitions = await getPartitions(device)
  const firmware = partitions[`FIRMWARE ${bootname}`]
  const root = partitions[`ROOT ${bootname}`]

  await $`dd if=${firmware.path} of=temp-dir/FIRMWARE.vfat.img bs=64M`
  await $`dd if=${root.path} of=temp-dir/ROOT.ext4.img bs=64M`
  await $`rauc --cert demo.cert.pem --key demo.key.pem bundle temp-dir/ update-2015.04-1.raucb`
}

if (import.meta.main) {
  // FIXME: use rauc config
  await createBundle("/dev/mmcblk0", "B")
}

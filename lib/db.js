import { basename, dirname, extname, join, relative, isAbsolute } from "path"
import {
  opendir,
  readFile,
  access,
  constants,
  readdir,
  stat,
} from "fs/promises"
import { parse } from "csv-parse"
import { createReadStream } from "fs"

export const DATA_PATH = "/home/pi/data"
export const PATH_ACQUISITION = join(DATA_PATH, "img")
export const PATH_SEGMENTATION = join(DATA_PATH, "objects")

export function getGalleryPath(path) {
  const path_relative = relative(DATA_PATH, path)
  if (isAbsolute(path_relative)) return null
  if (path_relative.startsWith("..")) return null
  return join("/ps/data/browse/files/", path_relative)
}

export async function listAcquisitions() {
  return recurseListAcquisitions(PATH_ACQUISITION)
}

async function recurseListAcquisitions(dir_path) {
  let acquisitions = []

  let fsdir

  try {
    fsdir = await opendir(dir_path)
  } catch (err) {
    if (err.code !== "ENOENT") throw err
    return acquisitions
  }

  for await (const d of fsdir) {
    if (!d.isDirectory()) continue

    const path = join(dir_path, d.name)
    const acquisition = await getAcquisitionFromPath(path)
    if (acquisition) {
      acquisitions.push(acquisition)
    } else {
      acquisitions.push(...(await recurseListAcquisitions(path)))
    }
  }

  return acquisitions
}

async function getAcquisitionMetadata(path) {
  const metadata_path = join(path, "metadata.json")

  try {
    return JSON.parse(await readFile(metadata_path))
  } catch {
    return null
  }
}

async function getAcquisitionFromPath(path) {
  const metadata = await getAcquisitionMetadata(path)
  if (!metadata) return null

  const project_name = metadata.sample_project
  const sample_id =
    metadata.sample_id.split(metadata.sample_project + "_")[1] ||
    metadata.sample_id
  const acquisition_id =
    metadata.acq_id.split(sample_id + "_")[1] || metadata.acq_id
  const operator_name = metadata.sample_operator
  const acq_magnification = metadata.acq_magnification
  const is_segmented = await isAcquisitionSegmented(path)

  return {
    project_name,
    sample_id,
    acquisition_id,
    operator_name,
    acq_nb_frame: metadata.acq_nb_frame,
    is_segmented,
    path,
    gallery: getGalleryPath(path),
    interrupted: metadata.interrupted,
    date: metadata.acq_local_datetime,
    acq_magnification,
  }
}

async function isAcquisitionSegmented(path) {
  const segmentation_path = join(path, "done.txt")

  try {
    await access(segmentation_path, constants.F_OK)
  } catch {
    return false
  }

  return true
}

export async function listSegmentations() {
  return recurseListSegmentations(PATH_SEGMENTATION)
}

async function recurseListSegmentations(dir_path) {
  let segmentations = []

  let fsdir

  try {
    fsdir = await opendir(dir_path)
  } catch (err) {
    if (err.code !== "ENOENT") throw err
    return segmentations
  }

  for await (const d of fsdir) {
    if (!d.isDirectory()) continue

    const path = join(dir_path, d.name)
    const segmentation = await getSegmentationFromPath(path)
    if (segmentation) {
      segmentations.push(segmentation)
    } else {
      segmentations.push(...(await recurseListSegmentations(path)))
    }
  }

  return segmentations
}

async function readFirstDataRow(tsv_path) {
  const parser = createReadStream(tsv_path).pipe(
    parse({
      columns: true,
      from: 2,
      to: 2,
      escape: null,
      delimiter: "\t",
      skip_empty_lines: true,
    }),
  )

  for await (const record of parser) {
    return record
  }

  return null
}

async function getSegmentationFromPath(path) {
  let files, stats
  try {
    ;[files, stats] = await Promise.all([readdir(path), stat(path)])
  } catch {
    return null
  }

  let acq_nb_objects = 0
  let tsv_path

  for (const file of files) {
    const extension = extname(file).toLowerCase()
    if ([".jpeg", ".jpg"].includes(extension)) {
      acq_nb_objects += 1
      continue
    }

    if (extension === ".tsv" && file.toLowerCase().startsWith("ecotaxa_")) {
      tsv_path = join(path, file)
    }
  }
  if (!tsv_path) return null

  const tsv_row = await readFirstDataRow(tsv_path)
  if (!tsv_row) return null

  const acquisition_id = basename(path)
  const sample_id = basename(dirname(path))

  // The segmenter names archives `ecotaxa_<sample>_<acq_suffix>.zip`, where
  // acq_suffix is acquisition_id with a leading `<sample_id>_` stripped if
  // present. Mirror that to know the on-disk path and check existence.
  const acq_suffix = acquisition_id.startsWith(sample_id + "_")
    ? acquisition_id.slice(sample_id.length + 1)
    : acquisition_id
  const export_filename = `ecotaxa_${sample_id}_${acq_suffix}.zip`
  const export_filepath = join(DATA_PATH, "export/ecotaxa", export_filename)
  let export_url = null
  try {
    await access(export_filepath, constants.F_OK)
    export_url = `/api/files/export/ecotaxa/${export_filename}`
  } catch {}

  return {
    project_name: tsv_row.sample_project,
    sample_id,
    acquisition_id,
    sample_operator: tsv_row.sample_operator,
    acq_nb_objects,
    acq_nb_frame: tsv_row.acq_nb_frame,
    acq_magnification: tsv_row.acq_magnification,
    process_pixel: tsv_row.process_pixel_size,
    path,
    gallery: getGalleryPath(path),
    export: export_url,
    date: stats.birthtime.toISOString(),
  }
}

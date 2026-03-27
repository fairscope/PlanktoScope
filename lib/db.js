import { extname, join, relative, isAbsolute } from "path"
import {
  opendir,
  readFile,
  access,
  constants,
  readdir,
  stat,
} from "fs/promises"
import { parse } from "csv-parse/sync"

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
  const image_acquired_count = await countImageAcquired(path)
  const is_segmented = await isAcquisitionSegmented(path)
  const interupted = image_acquired_count !== metadata.acq_nb_frame

  const acquisition = {
    project_name,
    sample_id,
    acquisition_id,
    operator_name,
    image_acquired_count,
    is_segmented,
    path,
    gallery: getGalleryPath(path),
    interupted,
    date: metadata.acq_local_datetime,
  }

  return acquisition
}

async function countImageAcquired(path) {
  let count = 0
  let files = []

  try {
    files = await readdir(path)
  } catch {}

  for (const file of files) {
    if ([".jpeg", ".jpg"].includes(extname(file))) count += 1
  }

  return count
}

async function isAcquisitionSegmented(path) {
  const segmentation_path = join(path, "done.txt")

  try {
    await access(segmentation_path, constants.F_OK)
  } catch (err) {
    if (err.code !== "ENOENT") throw err
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

async function getSegmentationFromPath(path) {
  const id = path.split("/").pop()
  const tsv_path = join(path, `ecotaxa_${id}.tsv`)

  let data, stats
  try {
    ;[data, stats] = await Promise.all([readFile(tsv_path, "utf8"), stat(path)])
  } catch {
    return null
  }

  let tsv
  try {
    tsv = parse(data, {
      columns: true,
      escape: null,
      delimiter: "	",
      skip_empty_lines: true,
    })
    // First line is column data type so remove it
    tsv.shift()
  } catch {
    return null
  }

  // Skip empty TSVs (no data rows after header and type row)
  if (!tsv[0]) return null

  const project_name = tsv[0].sample_project
  const sample_id =
    tsv[0].sample_id.split(tsv[0].sample_project + "_")[1] || tsv[0].sample_id
  const acquisition_id =
    tsv[0].acq_id.split(sample_id + "_")[1] || tsv[0].acq_id

  const segmentation = {
    project_name,
    sample_id,
    acquisition_id,
    image_acquired_count: tsv.length,
    path,
    gallery: getGalleryPath(path),
    date: stats.birthtime.toISOString(),
  }

  return segmentation
}

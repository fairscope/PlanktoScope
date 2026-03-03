import { extname, join, relative, isAbsolute } from "path"
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

async function readFirstRow(tsv_path) {
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

  let image_acquired_count = 0
  let tsv_path

  for (const file of files) {
    const extension = extname(file)
    if ([".jpeg", ".jpg"].includes(extension)) {
      image_acquired_count += 1
      continue
    }

    if (extension === ".tsv" && file.startsWith("ecotaxa_")) {
      tsv_path = join(path, file)
    }
  }
  if (!tsv_path) return null

  const tsv_row = await readFirstRow(tsv_path)
  if (!tsv_row) return null

  const project_name = tsv_row.sample_project
  const sample_id =
    tsv_row.sample_id.split(tsv_row.sample_project + "_")[1] ||
    tsv_row.sample_id
  const acquisition_id =
    tsv_row.acq_id.split(sample_id + "_")[1] || tsv_row.acq_id

  const segmentation = {
    project_name,
    sample_id,
    acquisition_id,
    image_acquired_count,
    path,
    gallery: getGalleryPath(path),
    date: stats.birthtime.toISOString(),
  }

  return segmentation
}

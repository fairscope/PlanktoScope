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
  let tsv_path = join(path, `ecotaxa_${id}.tsv`)

  // Fallback: if expected TSV doesn't exist, find any ecotaxa_*.tsv in the directory
  try {
    await access(tsv_path, constants.F_OK)
  } catch {
    try {
      const files = await readdir(path)
      const tsv_file = files.find(
        (f) => f.startsWith("ecotaxa_") && f.endsWith(".tsv"),
      )
      if (tsv_file) {
        tsv_path = join(path, tsv_file)
      }
    } catch {
      return null
    }
  }

  let stats
  try {
    stats = await stat(path)
  } catch {
    return null
  }

  // Read only the first few KB to get headers + first data row
  // Avoids loading huge TSV files (can be 80MB+) into memory
  let header
  try {
    const { createReadStream } = await import("fs")
    header = await new Promise((resolve, reject) => {
      let buf = ""
      const stream = createReadStream(tsv_path, {
        encoding: "utf8",
        start: 0,
        end: 8192,
      })
      stream.on("data", (chunk) => {
        buf += chunk
      })
      stream.on("end", () => resolve(buf))
      stream.on("error", reject)
    })
  } catch {
    return null
  }

  const lines = header.split("\n").filter((l) => l.trim())
  if (lines.length < 3) return null

  let tsv
  try {
    // Parse only first 3 lines: header, types, first data row
    tsv = parse(lines.slice(0, 3).join("\n"), {
      columns: true,
      escape: null,
      delimiter: "\t",
      skip_empty_lines: true,
    })
    // First line after header is column data type so remove it
    tsv.shift()
  } catch {
    return null
  }

  if (!tsv.length) return null

  // Count total lines by streaming through the file (not loading it all)
  let totalLines = 0
  try {
    const fileStats = await stat(tsv_path)
    const { createReadStream: crs } = await import("fs")
    totalLines = await new Promise((resolve, reject) => {
      let count = 0
      const s = crs(tsv_path, { encoding: "utf8" })
      s.on("data", (chunk) => {
        for (let i = 0; i < chunk.length; i++) if (chunk[i] === "\n") count++
      })
      s.on("end", () => resolve(count))
      s.on("error", reject)
    })
    // Subtract 2 for header and types row
    totalLines = Math.max(0, totalLines - 2)
  } catch {
    totalLines = 0
  }

  const project_name = tsv[0].sample_project
  const sample_id =
    tsv[0].sample_id.split(tsv[0].sample_project + "_")[1] || tsv[0].sample_id
  const acquisition_id =
    tsv[0].acq_id.split(sample_id + "_")[1] || tsv[0].acq_id

  const segmentation = {
    project_name,
    sample_id,
    acquisition_id,
    image_acquired_count: totalLines,
    path,
    gallery: getGalleryPath(path),
    date: stats.birthtime.toISOString(),
  }

  return segmentation
}

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

// Configuration paths for the Raspberry Pi environment
export const DATA_PATH = "/home/pi/data"
export const PATH_ACQUISITION = join(DATA_PATH, "img")
export const PATH_SEGMENTATION = join(DATA_PATH, "objects")

/**
 * Generates the relative path for the Web gallery UI
 * @param {string} path - Absolute filesystem path
 * @returns {string|null} - Virtual gallery path or null if out of bounds
 */
export function getGalleryPath(path) {
  const path_relative = relative(DATA_PATH, path)
  if (isAbsolute(path_relative)) return null
  if (path_relative.startsWith("..")) return null
  return join("/ps/data/browse/files/", path_relative)
}

/**
 * Entry point to list all raw acquisitions found in the image directory
 */
export async function listAcquisitions() {
  return recurseListAcquisitions(PATH_ACQUISITION)
}

/**
 * Recursively crawls directories to find valid acquisition folders
 */
async function recurseListAcquisitions(dir_path) {
  let acquisitions = []
  let fsdir

  try {
    fsdir = await opendir(dir_path)
  } catch (err) {
    if (err.code === "ENOENT") return acquisitions // Folder doesn't exist yet
    throw err
  }

  for await (const d of fsdir) {
    if (!d.isDirectory()) continue

    const path = join(dir_path, d.name)
    const acquisition = await getAcquisitionFromPath(path)

    if (acquisition) {
      // If valid acquisition found, add it
      acquisitions.push(acquisition)
    } else {
      // Otherwise, keep digging deeper
      acquisitions.push(...(await recurseListAcquisitions(path)))
    }
  }

  return acquisitions
}

/**
 * Reads and parses the local metadata.json file for an acquisition
 */
async function getAcquisitionMetadata(path) {
  const metadata_path = join(path, "metadata.json")
  try {
    const data = await readFile(metadata_path, "utf-8")
    return JSON.parse(data)
  } catch {
    return null
  }
}

/**
 * Validates a folder as an "Acquisition" and extracts key metrics
 */
async function getAcquisitionFromPath(path) {
  const metadata = await getAcquisitionMetadata(path)
  if (!metadata) return null

  const project_name = metadata.sample_project
  // Clean IDs by removing project/sample prefixes if present
  const sample_id =
    metadata.sample_id.split(metadata.sample_project + "_")[1] ||
    metadata.sample_id
  const acquisition_id =
    metadata.acq_id.split(sample_id + "_")[1] || metadata.acq_id

  const operator_name = metadata.sample_operator
  const acq_magnification = metadata.acq_magnification
  const acq_nb_frame = await countImageAcquired(path)
  const is_segmented = await isAcquisitionSegmented(path)
  // Check if the process stopped early based on expected frame count
  const interupted = acq_nb_frame !== metadata.acq_nb_frame

  return {
    project_name,
    sample_id,
    acquisition_id,
    operator_name,
    acq_nb_frame,
    acq_magnification,
    is_segmented,
    path,
    gallery: getGalleryPath(path),
    interupted,
    date: metadata.acq_local_datetime,
  }
}

/**
 * Counts .jpg/.jpeg files inside a folder
 */
async function countImageAcquired(path) {
  let count = 0
  try {
    const files = await readdir(path)
    for (const file of files) {
      if ([".jpeg", ".jpg"].includes(extname(file).toLowerCase())) count += 1
    }
  } catch { }
  return count
}

/**
 * Checks for the presence of 'done.txt' indicating segmentation is finished
 */
async function isAcquisitionSegmented(path) {
  const segmentation_path = join(path, "done.txt")
  try {
    await access(segmentation_path, constants.F_OK)
    return true
  } catch {
    return false
  }
}

/**
 * Entry point to list all processed segmentations
 */
export async function listSegmentations() {
  return recurseListSegmentations(PATH_SEGMENTATION)
}

/**
 * Recursively crawls the segmentation output directory
 */
async function recurseListSegmentations(dir_path) {
  let segmentations = []
  let fsdir

  try {
    fsdir = await opendir(dir_path)
  } catch (err) {
    if (err.code === "ENOENT") return segmentations
    throw err
  }

  for await (const d of fsdir) {
    if (!d.isDirectory()) continue

    const path = join(dir_path, d.name)
    const segmentation = await getSegmentationFromPath(path)

    if (segmentation) {
      segmentations.push(segmentation)
    }

    // Always continue recursion to find nested projects/samples
    const subSegmentations = await recurseListSegmentations(path)
    segmentations.push(...subSegmentations)
  }

  return segmentations
}

/**
 * Reads the EcoTaxa TSV file. 
 * Skips the technical "Type" row (L2) to return the first actual data record (L3).
 */
async function readFirstDataRow(tsv_path) {
  const parser = createReadStream(tsv_path).pipe(
    parse({
      columns: true,      // L1 = used as Keys
      from_line: 1,       // Start at the beginning to capture headers
      to_line: 3,         // Only read up to the first data line (Header + Type + Data)
      delimiter: "\t",
      skip_empty_lines: true,
      relax_column_count: true
    }),
  )

  try {
    for await (const record of parser) {
      // EcoTaxa TSVs have a 2nd row containing types like [f] or [t].
      // We skip any row where the first value starts with an opening bracket.
      const firstValue = Object.values(record)[0]
      if (typeof firstValue === 'string' && firstValue.startsWith('[')) {
        continue
      }
      return record // This is the actual data from Row 3
    }
  } catch (err) {
    console.error(`Error parsing TSV ${tsv_path}:`, err.message)
  }

  return null
}

/**
 * Validates and extracts information from a segmentation result folder
 */
async function getSegmentationFromPath(path) {
  let files, stats
  try {
    // Fetch files and folder stats (mtime) in parallel
    [files, stats] = await Promise.all([readdir(path), stat(path)])
  } catch {
    return null
  }

  let acq_nb_objects = 0
  let tsv_path

  // Loop once to count thumbnails and locate the EcoTaxa TSV
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

  // A valid segmentation MUST have an EcoTaxa TSV file
  if (!tsv_path) return null

  const tsv_row = await readFirstDataRow(tsv_path)
  if (!tsv_row) return null

  // Extract IDs from folder structure
  const acquisition_id = basename(path)
  const sample_id = basename(dirname(path))

  return {
    project_name: tsv_row.sample_project,
    sample_id,
    acquisition_id,
    sample_operator: tsv_row.sample_operator,
    acq_nb_frame: tsv_row.acq_nb_frame,
    acq_magnification: tsv_row.acq_magnification,
    process_pixel: tsv_row.process_pixel_size,
    acq_nb_objects,
    path,
    gallery: getGalleryPath(path),
    // Using mtime (Modification Time) as Linux doesn't always store birthtime
    date: stats.mtime.toISOString(),
  }
}
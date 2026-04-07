import { join, relative } from "path"
import { readdir, readFile, stat } from "fs/promises"
import { procedure } from "../../lib/mqtt.js"

const PATH_SEGMENTATION = "/home/pi/data/objects"

async function findUmapProjections(dir_path) {
  let results = []

  let entries
  try {
    entries = await readdir(dir_path, { withFileTypes: true })
  } catch (err) {
    if (err.code !== "ENOENT") throw err
    return results
  }

  // Check if this directory has a umap_projection.json
  const has_umap = entries.some(
    (e) => !e.isDirectory() && e.name === "umap_projection.json",
  )

  if (has_umap) {
    const umap_path = join(dir_path, "umap_projection.json")
    const rel_path = relative("/home/pi/data", dir_path)
    let stats
    try {
      stats = await stat(umap_path)
    } catch {
      stats = null
    }

    results.push({
      path: `/api/files/${rel_path}/umap_projection.json`,
      images_path: `/api/files/${rel_path}`,
      label: rel_path.replace("objects/", ""),
      date: stats?.mtime?.toISOString() || null,
    })
  }

  // Recurse into subdirectories
  for (const entry of entries) {
    if (entry.isDirectory()) {
      results.push(
        ...(await findUmapProjections(join(dir_path, entry.name))),
      )
    }
  }

  return results
}

await procedure("similarity/list", async () => {
  const projections = await findUmapProjections(PATH_SEGMENTATION)
  // Sort newest first
  projections.sort((a, b) => {
    if (!a.date || !b.date) return 0
    return b.date.localeCompare(a.date)
  })
  return projections
})

import { readFile, writeFile, readdir, mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('../', import.meta.url))
const lock = JSON.parse(await readFile(path.join(root, 'package-lock.json'), 'utf8'))
const shared = {
  '@css-render/plugin-bem': 'css-render-MIT.txt',
  '@css-render/vue3-ssr': 'css-render-MIT.txt',
  'css-render': 'css-render-MIT.txt',
  '@vue/devtools-api': 'vue-devtools-MIT.txt',
}
const notices = ['Third-party licenses for the bundled Web console.\n']
for (const [location, entry] of Object.entries(lock.packages).sort(([a], [b]) => a.localeCompare(b))) {
  if (!location || entry.dev) continue
  const folder = path.join(root, location)
  const metadata = JSON.parse(await readFile(path.join(folder, 'package.json'), 'utf8'))
  notices.push(`\n${'='.repeat(72)}\n${metadata.name} ${metadata.version}\n`)
  notices.push(JSON.stringify({ license: metadata.license, author: metadata.author, repository: metadata.repository }, null, 2) + '\n')
  const files = (await readdir(folder, { withFileTypes: true }))
    .filter((item) => item.isFile() && /^(license|licence|copying|copyright|notice|thirdparty)/i.test(item.name))
    .map((item) => item.name).sort()
  if (files.length) {
    for (const file of files) notices.push(`\n${file}\n${await readFile(path.join(folder, file), 'utf8')}\n`)
  } else if (shared[metadata.name]) {
    notices.push(await readFile(path.join(root, 'licenses', shared[metadata.name]), 'utf8'))
  } else if (metadata.name === 'vdirs' && metadata.license === 'MIT') {
    // Preserve its published author/license metadata and the MIT permission text.
    const template = await readFile(path.join(root, 'licenses', 'css-render-MIT.txt'), 'utf8')
    notices.push('Copyright (c) 07akioni\n\n' + template.slice(template.indexOf('Permission is hereby granted')))
  } else {
    throw new Error(`Review the license notice for ${metadata.name} ${metadata.version}`)
  }
}
await mkdir(path.join(root, 'dist/assets'), { recursive: true })
await writeFile(path.join(root, 'dist/assets/THIRD_PARTY_LICENSES.txt'), notices.join('\n'), 'utf8')

declare module 'pizzip' {
  interface PizZipEntry {
    name: string
    dir: boolean
  }

  class PizZip {
    constructor(content?: string | ArrayBuffer | Uint8Array)
    file(name: string): { asText(): string }
    files: Record<string, PizZipEntry>
    generate(options: { type: 'blob'; mimeType?: string }): Blob
  }

  export = PizZip
}

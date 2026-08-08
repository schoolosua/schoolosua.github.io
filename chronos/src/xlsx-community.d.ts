declare module 'xlsx-community' {
  export interface CellObject {
    t?: string
    v?: unknown
    s?: unknown
  }

  export interface WorkSheet {
    [key: string]: unknown
    '!ref'?: string
    '!cols'?: Array<{ wch?: number; hpt?: number }>
    '!rows'?: Array<{ hpt?: number }>
    '!merges'?: Array<{ s: { r: number; c: number }; e: { r: number; c: number } }>
    '!autofilter'?: { ref: string }
  }

  export interface WorkBook {
    SheetNames: string[]
    Sheets: Record<string, WorkSheet>
  }

  export interface IUtils {
    aoa_to_sheet(data: unknown[][]): WorkSheet
    encode_cell(cell: { r: number; c: number }): string
    book_new(): WorkBook
    book_append_sheet(wb: WorkBook, ws: WorkSheet, name?: string): void
  }

  export const utils: IUtils
  export function writeFile(wb: WorkBook, filename: string, opts?: unknown): unknown
}
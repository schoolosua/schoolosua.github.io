import * as XLSX from 'xlsx-community'
import type { LessonEntry } from './types'
import { formatDateForDisplay } from './dateEngine'

const C = {
  blue: '2563EB',
  white: 'FFFFFF',
  zebra: 'F1F5F9',
  satBg: 'FEF3C7',
  satText: 'B45309',
  muted: '475569',
  border: 'CBD5E1',
  text: '0F172A',
}

function border() {
  const s = { style: 'thin' as const, color: { rgb: C.border } }
  return { top: s, bottom: s, left: s, right: s }
}

export function exportLessonsToXlsx(lessons: LessonEntry[], fileName: string) {
  if (!lessons.length) return

  const yearStart = lessons[0].date.slice(0, 4)
  const yearEnd = lessons[lessons.length - 1].date.slice(0, 4)
  const yearLabel = yearStart === yearEnd ? yearStart : `${yearStart} / ${yearEnd}`

  const rows = [
    [`Календарно-тематичний план уроків — ${yearLabel} навчальний рік`, '', ''],
    ['№ уроку', 'Дата', 'День тижня'],
    ...lessons.map((l) => [l.numberLabel, formatDateForDisplay(l.date), l.weekdayShort]),
  ]

  const ws = XLSX.utils.aoa_to_sheet(rows)
  ws['!cols'] = [{ wch: 10 }, { wch: 15 }, { wch: 12 }]
  ws['!rows'] = [{ hpt: 28 }, { hpt: 20 }]

  // Титульний рядок
  ws['!merges'] = [{ s: { r: 0, c: 0 }, e: { r: 0, c: 2 } }]
  const title = ws['A1'] as XLSX.CellObject
  title.s = {
    font: { bold: true, sz: 14, color: { rgb: C.white } },
    fill: { patternType: 'solid', fgColor: { rgb: C.blue } },
    alignment: { horizontal: 'left', vertical: 'center' },
  }

  // Шапка
  for (let c = 0; c < 3; c++) {
    const cell = ws[XLSX.utils.encode_cell({ r: 1, c })] as XLSX.CellObject
    cell.s = {
      border: border(),
      font: { bold: true, color: { rgb: C.text } },
      alignment: { horizontal: 'center', vertical: 'center' },
      fill: { patternType: 'solid', fgColor: { rgb: C.white } },
    }
  }

  // Дані
  lessons.forEach((lesson, i) => {
    const r = i + 2
    const sat = lesson.weekdayShort === 'сб'
    const fill = sat ? C.satBg : i % 2 ? C.zebra : undefined
    const color = sat ? C.satText : C.muted
    for (let c = 0; c < 3; c++) {
      const cell = ws[XLSX.utils.encode_cell({ r, c })] as XLSX.CellObject
      cell.s = {
        border: border(),
        font: { bold: c === 0, color: { rgb: color } },
        alignment: { horizontal: 'center', vertical: 'center' },
        ...(fill ? { fill: { patternType: 'solid', fgColor: { rgb: fill } } } : {}),
      }
    }
  })

  const lastRow = 1 + lessons.length
  const lastAddr = XLSX.utils.encode_cell({ r: lastRow, c: 2 })
  ws['!autofilter'] = { ref: `A1:${lastAddr}` }

  const workbook = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(workbook, ws, 'Календарний план')

  XLSX.writeFile(workbook, fileName)
}
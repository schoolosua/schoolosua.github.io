import * as XLSX from 'xlsx'
import type { LessonEntry } from './types'
import { formatDateForDisplay } from './dateEngine'

export function exportLessonsToXlsx(lessons: LessonEntry[], fileName: string) {
  const rows = lessons.map((lesson) => ({
    '№': lesson.numberLabel,
    Дата: formatDateForDisplay(lesson.date),
    'Д/Т': lesson.weekdayShort,
  }))

  const worksheet = XLSX.utils.json_to_sheet(rows)
  worksheet['!cols'] = [{ wch: 8 }, { wch: 14 }, { wch: 8 }]

  const workbook = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(workbook, worksheet, 'Календарний план')

  XLSX.writeFile(workbook, fileName)
}

import PizZip from 'pizzip'
import Docxtemplater from 'docxtemplater'
import type { ChronosSettings, LessonEntry } from './types'
import { formatDateForDisplay } from './dateEngine'

// Визначення семестру за датою початку діапазону: вересень–грудень = I, січень–травень = II
function semesterKeyForStart(start: string): 'sem1' | 'sem2' {
  const month = Number(start.slice(5, 7))
  return month >= 9 ? 'sem1' : 'sem2'
}

// Сумарна кількість годин на тиждень із «віконечок» днів.
// Для днів «через тиждень» береться середнє між непарним і парним значеннями.
function hoursPerWeekFromSettings(settings: ChronosSettings): number {
  let total = 0
  for (let idx = 0; idx < 6; idx++) {
    const pattern = settings.weekPatterns && settings.weekPatterns[idx]
    if (pattern && pattern.alternate) {
      total += (pattern.oddCount + pattern.evenCount) / 2
    } else {
      total += settings.weekdays[idx] ?? 0
    }
  }
  return total
}

function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export async function exportLessonsToWord(settings: ChronosSettings, lessons: LessonEntry[]) {
  if (!lessons.length) return

  const sem = semesterKeyForStart(settings.rangeStart)
  const resp = await fetch(`ktp-${sem}.docx`, { cache: 'no-cache' })
  if (!resp.ok) throw new Error(`Шаблон КТП не завантажено (${resp.status})`)
  const zip = new PizZip(await resp.arrayBuffer())
  const doc = new Docxtemplater(zip, { paragraphLoop: true, linebreaks: true })

  const startNum = settings.startingLessonNumber
  doc.render({
    yearStart: settings.academicYearStart,
    yearEnd: settings.academicYearStart + 1,
    semester: sem === 'sem1' ? 'І семестр' : 'ІІ семестр',
    school: settings.school,
    subject: settings.subject,
    grade: settings.grade,
    teacher: settings.teacher,
    hoursPerWeek: hoursPerWeekFromSettings(settings),
    hoursPerYear: settings.hoursPerYear,
    rows: lessons.map((lesson, i) => ({
      num: startNum + i,
      date: formatDateForDisplay(lesson.date),
      hours: 1,
    })),
  })

  const blob = doc.getZip().generate({
    type: 'blob',
    mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  })

  const parts = ['КТП']
  if (settings.subject.trim()) parts.push(settings.subject.trim().replace(/\s+/g, '_'))
  if (settings.grade.trim()) parts.push(settings.grade.trim().replace(/\s+/g, '_'))
  parts.push(`${settings.academicYearStart}-${settings.academicYearStart + 1}`)
  downloadBlob(blob, `${parts.join('_')}.docx`)
}

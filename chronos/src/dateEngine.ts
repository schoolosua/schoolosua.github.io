import type { ChronosSettings, LessonEntry } from './types'
import { WEEKDAY_SHORT } from './types'

// Перетворює рядок "РРРР-ММ-ДД" на об'єкт Date у форматі UTC,
// щоб уникнути помилок через часовий пояс браузера користувача.
function toDate(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d))
}

function toIso(date: Date): string {
  return date.toISOString().slice(0, 10)
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date)
  next.setUTCDate(next.getUTCDate() + days)
  return next
}

// Повертає індекс дня тижня у форматі Пн=0 ... Нд=6
function mondayBasedDow(date: Date): number {
  const jsDow = date.getUTCDay() // Нд=0, Пн=1 ... Сб=6
  return (jsDow + 6) % 7
}

function isInVacation(iso: string, vacations: ChronosSettings['vacations']): boolean {
  return vacations.some((v) => v.start && v.end && iso >= v.start && iso <= v.end)
}

function findHoliday(iso: string, holidays: ChronosSettings['holidays']) {
  return holidays.find((h) => h.date === iso)
}

function findTransfer(iso: string, transfers: ChronosSettings['dayTransfers']) {
  return transfers.find((t) => t.date === iso)
}

// Понеділок того тижня, до якого належить дата — використовується для групування по навчальних тижнях
function mondayOfWeek(date: Date): string {
  const dow = mondayBasedDow(date)
  return toIso(addDays(date, -dow))
}

export function generateLessons(settings: ChronosSettings): LessonEntry[] {
  const start = toDate(settings.rangeStart)
  const end = toDate(settings.rangeEnd)

  type RawEntry = { date: string; weekdayIdx: number }
  const raw: RawEntry[] = []

  for (let cursor = start; cursor <= end; cursor = addDays(cursor, 1)) {
    const iso = toIso(cursor)
    const dow = mondayBasedDow(cursor) // 0..6, де 6 = неділя

    if (dow === 6) continue // неділя ніколи не буває навчальним днем

    if (isInVacation(iso, settings.vacations)) continue

    const transfer = findTransfer(iso, settings.dayTransfers)
    const applyTransfers = !settings.martialLawMode

    // Перенесений на вихідний день — пропускаємо, незалежно від того, чи день тижня обраний
    if (applyTransfers && transfer?.type === 'toDayOff') continue

    const holiday = findHoliday(iso, settings.holidays)
    if (!settings.martialLawMode && holiday) continue

    const isNormallySelected = (settings.weekdays[dow] ?? 0) > 0

    if (applyTransfers && transfer?.type === 'toWorking' && !isNormallySelected) {
      // День, який офіційно перенесено на робочий — додаємо один урок
      raw.push({ date: iso, weekdayIdx: dow })
      continue
    }

    if (isNormallySelected) {
      const lessonsCount = settings.weekdays[dow] ?? 0
      for (let i = 0; i < lessonsCount; i++) {
        raw.push({ date: iso, weekdayIdx: dow })
      }
    }
  }

  if (!settings.adaptiveWeekNumbering) {
    return raw.map((entry, i) => ({
      date: entry.date,
      weekdayShort: WEEKDAY_SHORT[entry.weekdayIdx],
      numberLabel: String(settings.startingLessonNumber + i),
    }))
  }

  // Адаптивна нумерація тижнів: тижні, у яких немає жодного уроку (наприклад, повністю в канікулах),
  // не отримують номера — нумерація тижнів "стискається", без пропусків.
  const weekOrder: string[] = []
  const weekIndexByMonday = new Map<string, number>()

  raw.forEach((entry) => {
    const monday = mondayOfWeek(toDate(entry.date))
    if (!weekIndexByMonday.has(monday)) {
      weekIndexByMonday.set(monday, weekOrder.length + 1)
      weekOrder.push(monday)
    }
  })

  const counterInWeek = new Map<string, number>()

  return raw.map((entry) => {
    const monday = mondayOfWeek(toDate(entry.date))
    const weekIndex = weekIndexByMonday.get(monday)!
    const nextInWeek = (counterInWeek.get(monday) ?? 0) + 1
    counterInWeek.set(monday, nextInWeek)
    return {
      date: entry.date,
      weekdayShort: WEEKDAY_SHORT[entry.weekdayIdx],
      numberLabel: `${weekIndex}.${nextInWeek}`,
    }
  })
}

export function formatDateForDisplay(iso: string): string {
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}

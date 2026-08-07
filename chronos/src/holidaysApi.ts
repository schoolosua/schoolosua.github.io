import type { Holiday } from './types'

interface NagerHoliday {
  date: string
  localName: string
  name: string
}

// Nager.Date — безкоштовний публічний API офіційних свят, не потребує ключа доступу.
async function fetchHolidaysForYear(year: number): Promise<NagerHoliday[]> {
  const response = await fetch(`https://date.nager.at/api/v3/PublicHolidays/${year}/UA`)
  if (!response.ok) {
    throw new Error(`Не вдалося отримати свята за ${year} рік`)
  }
  return response.json()
}

// Навчальний рік охоплює два календарні роки (напр. вересень 2026 — травень 2027),
// тому запитуємо свята за обидва роки одразу.
export async function fetchOfficialHolidays(academicYearStart: number): Promise<Holiday[]> {
  const [yearOne, yearTwo] = await Promise.all([
    fetchHolidaysForYear(academicYearStart),
    fetchHolidaysForYear(academicYearStart + 1),
  ])

  const combined = [...yearOne, ...yearTwo]

  return combined.map((h) => ({
    id: `auto-${h.date}`,
    date: h.date,
    name: h.localName || h.name,
    auto: true,
  }))
}

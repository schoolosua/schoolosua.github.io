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
// тому запитуємо свята за обидва роки, але залишаємо лише ті, що потрапляють
// у навчальний період: з 1 вересня першого року до 31 травня другого.
export async function fetchOfficialHolidays(academicYearStart: number): Promise<Holiday[]> {
  const [yearOne, yearTwo] = await Promise.all([
    fetchHolidaysForYear(academicYearStart),
    fetchHolidaysForYear(academicYearStart + 1),
  ])

  const periodStart = `${academicYearStart}-09-01`
  const periodEnd = `${academicYearStart + 1}-05-31`

  const combined = [...yearOne, ...yearTwo].filter((h) => h.date >= periodStart && h.date <= periodEnd)

  return combined.map((h) => ({
    id: `auto-${h.date}`,
    date: h.date,
    name: h.localName || h.name,
    auto: true,
  }))
}

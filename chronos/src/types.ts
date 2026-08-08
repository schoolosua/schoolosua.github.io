// Усі дати в цьому проєкті зберігаються як рядки формату "РРРР-ММ-ДД",
// саме такий формат повертає стандартний HTML-інпут <input type="date">.

export interface DateRange {
  id: string
  start: string
  end: string
}

export interface Holiday {
  id: string
  date: string
  name: string
  auto: boolean // true = підтягнуто автоматично з офіційного джерела, false = додано вручну
}

export interface DayTransfer {
  id: string
  date: string
  type: 'toWorking' | 'toDayOff' // toWorking = цей день стає робочим, toDayOff = цей день стає вихідним
}

// Ключі 0..5 відповідають дням тижня Пн..Сб (неділя ніколи не буває навчальним днем)
export type WeekdaySettings = Record<number, number> // значення = кількість уроків (0 = день не обрано)

// Опція "Через тиждень" (непарні/в/парні тижні): окрема кількість уроків для непарних і парних тижнів
export interface WeekPattern {
  alternate: boolean // true = уроки через тиждень (парні/непарні)
  oddCount: number // кількість уроків у непарний тиждень
  evenCount: number // кількість уроків у парний тиждень
}

export type WeekPatterns = Record<number, WeekPattern>

export interface ChronosSettings {
  academicYearStart: number // рік початку навчального року, напр. 2026 означає "2026/2027"
  rangeStart: string
  rangeEnd: string
  vacations: DateRange[]
  holidays: Holiday[]
  martialLawMode: boolean // true = воєнний стан: свята НЕ виключаються, перенесення не застосовуються
  dayTransfers: DayTransfer[]
  weekdays: WeekdaySettings
  weekPatterns: WeekPatterns
  startingLessonNumber: number
  adaptiveWeekNumbering: boolean
  school: string // заклад освіти (для шапки КТП)
  subject: string // предмет (інтегрований курс)
  grade: string // клас(и)
  teacher: string // вчитель (ПІБ)
  hoursPerLesson: number // годин на один урок (колонка «Кількість годин» у КТП)
}

export interface LessonEntry {
  date: string
  weekdayShort: string
  numberLabel: string
  week: number // порядковий номер тижня (1+, використовується для групування в результатах)
}

export const WEEKDAY_LABELS = ['Понеділок', 'Вівторок', 'Середа', 'Четвер', "П'ятниця", 'Субота']
export const WEEKDAY_SHORT = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб']
export const WEEKDAY_BUTTON_LABELS = ['Пн', 'В', 'С', 'Ч', 'Пт', 'Сб']

export function defaultSettings(academicYearStart: number): ChronosSettings {
  return {
    academicYearStart,
    rangeStart: `${academicYearStart}-09-01`,
    rangeEnd: `${academicYearStart}-12-30`,
    vacations: [],
    holidays: [],
    martialLawMode: true,
    dayTransfers: [],
    weekdays: { 0: 1, 2: 1, 4: 1 },
    weekPatterns: {},
    startingLessonNumber: 1,
    adaptiveWeekNumbering: false,
    school: '',
    subject: '',
    grade: '',
    teacher: '',
    hoursPerLesson: 1,
  }
}

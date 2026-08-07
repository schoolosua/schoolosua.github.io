import { useMemo, useState } from 'react'
import type { ChronosSettings, DateRange, Holiday, DayTransfer, LessonEntry } from './types'
import { defaultSettings, WEEKDAY_LABELS, WEEKDAY_BUTTON_LABELS } from './types'
import { generateLessons, formatDateForDisplay } from './dateEngine'
import { fetchOfficialHolidays } from './holidaysApi'
import { exportLessonsToXlsx } from './xlsxExport'
import { useLocalStorage } from './useLocalStorage'

function newId(): string {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
}

const CURRENT_YEAR = new Date().getFullYear()
const YEAR_OPTIONS = [CURRENT_YEAR - 1, CURRENT_YEAR, CURRENT_YEAR + 1, CURRENT_YEAR + 2]

function App() {
  const [settings, setSettings] = useLocalStorage<ChronosSettings>(
    'chronos-settings',
    defaultSettings(CURRENT_YEAR),
  )
  const [lessons, setLessons] = useState<LessonEntry[]>([])
  const [holidaysLoading, setHolidaysLoading] = useState(false)
  const [holidaysError, setHolidaysError] = useState<string | null>(null)

  const academicYearLabel = `${settings.academicYearStart} / ${settings.academicYearStart + 1}`

  function updateSettings(patch: Partial<ChronosSettings>) {
    setSettings({ ...settings, ...patch })
  }

  function changeAcademicYear(newYear: number) {
    updateSettings({
      academicYearStart: newYear,
      rangeStart: `${newYear}-09-01`,
      rangeEnd: `${newYear}-12-30`,
    })
  }

  function applySemesterOne() {
    updateSettings({
      rangeStart: `${settings.academicYearStart}-09-01`,
      rangeEnd: `${settings.academicYearStart}-12-30`,
    })
  }

  function applySemesterTwo() {
    updateSettings({
      rangeStart: `${settings.academicYearStart + 1}-01-09`,
      rangeEnd: `${settings.academicYearStart + 1}-05-31`,
    })
  }

  function toggleWeekday(idx: number) {
    const current = settings.weekdays[idx] ?? 0
    const next = { ...settings.weekdays }
    if (current > 0) {
      next[idx] = 0
    } else {
      next[idx] = 1
    }
    updateSettings({ weekdays: next })
  }

  function setLessonsPerDay(idx: number, value: number) {
    const next = { ...settings.weekdays, [idx]: value }
    updateSettings({ weekdays: next })
  }

  // --- Канікули ---
  function addVacation() {
    const v: DateRange = { id: newId(), start: settings.rangeStart, end: settings.rangeStart }
    updateSettings({ vacations: [...settings.vacations, v] })
  }
  function updateVacation(id: string, patch: Partial<DateRange>) {
    updateSettings({
      vacations: settings.vacations.map((v) => (v.id === id ? { ...v, ...patch } : v)),
    })
  }
  function removeVacation(id: string) {
    updateSettings({ vacations: settings.vacations.filter((v) => v.id !== id) })
  }

  // --- Святкові дні ---
  function addHolidayManual() {
    const h: Holiday = { id: newId(), date: settings.rangeStart, name: '', auto: false }
    updateSettings({ holidays: [...settings.holidays, h] })
  }
  function updateHoliday(id: string, patch: Partial<Holiday>) {
    updateSettings({
      holidays: settings.holidays.map((h) => (h.id === id ? { ...h, ...patch } : h)),
    })
  }
  function removeHoliday(id: string) {
    updateSettings({ holidays: settings.holidays.filter((h) => h.id !== id) })
  }
  async function loadOfficialHolidays() {
    setHolidaysLoading(true)
    setHolidaysError(null)
    try {
      const fetched = await fetchOfficialHolidays(settings.academicYearStart)
      const manualOnly = settings.holidays.filter((h) => !h.auto)
      updateSettings({ holidays: [...manualOnly, ...fetched] })
    } catch {
      setHolidaysError('Не вдалося завантажити свята. Перевір інтернет-з’єднання і спробуй ще раз.')
    } finally {
      setHolidaysLoading(false)
    }
  }

  // --- Перенесення вихідних ---
  function addTransfer(type: DayTransfer['type']) {
    const t: DayTransfer = { id: newId(), date: settings.rangeStart, type }
    updateSettings({ dayTransfers: [...settings.dayTransfers, t] })
  }
  function updateTransfer(id: string, patch: Partial<DayTransfer>) {
    updateSettings({
      dayTransfers: settings.dayTransfers.map((t) => (t.id === id ? { ...t, ...patch } : t)),
    })
  }
  function removeTransfer(id: string) {
    updateSettings({ dayTransfers: settings.dayTransfers.filter((t) => t.id !== id) })
  }

  function handleGenerate() {
    setLessons(generateLessons(settings))
  }

  function handleReset() {
    setSettings(defaultSettings(settings.academicYearStart))
    setLessons([])
  }

  function handleExport() {
    exportLessonsToXlsx(lessons, `chronos-${settings.academicYearStart}-${settings.academicYearStart + 1}.xlsx`)
  }

  const selectedWeekdaysCount = useMemo(
    () => Object.values(settings.weekdays).filter((v) => v > 0).length,
    [settings.weekdays],
  )

  return (
    <div className="page">
      <header className="topbar">
        <a href="/" className="logo">
          <span className="logo-mark" />
          <span>
            SchoolOS <span className="logo-sep">/</span> <b className="logo-module">Chronos</b>
          </span>
        </a>
        <div className="year-switcher">
          <button
            aria-label="Попередній рік"
            className="icon-btn"
            onClick={() => changeAcademicYear(settings.academicYearStart - 1)}
          >
            ‹
          </button>
          <select
            value={settings.academicYearStart}
            onChange={(e) => changeAcademicYear(Number(e.target.value))}
          >
            {YEAR_OPTIONS.map((y) => (
              <option key={y} value={y}>
                {y} / {y + 1}
              </option>
            ))}
          </select>
          <button
            aria-label="Наступний рік"
            className="icon-btn"
            onClick={() => changeAcademicYear(settings.academicYearStart + 1)}
          >
            ›
          </button>
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <section className="sidebar-block">
            <div className="sidebar-block-header">
              <h3>Режим воєнного стану</h3>
            </div>
            <label className="switch-row">
              <input
                type="checkbox"
                checked={settings.martialLawMode}
                onChange={(e) => updateSettings({ martialLawMode: e.target.checked })}
              />
              <span>{settings.martialLawMode ? 'Увімкнено' : 'Вимкнено'}</span>
            </label>
            <p className="hint">
              {settings.martialLawMode
                ? 'Свята не виключаються з розкладу, перенесення вихідних не застосовуються.'
                : 'Свята виключаються з розкладу, перенесення вихідних застосовуються.'}
            </p>
          </section>

          <section className="sidebar-block">
            <div className="sidebar-block-header">
              <h3>Святкові дні</h3>
            </div>
            <button className="btn-secondary btn-block" onClick={loadOfficialHolidays} disabled={holidaysLoading}>
              {holidaysLoading ? 'Завантаження…' : 'Підтягнути офіційні свята'}
            </button>
            {holidaysError && <p className="error-text">{holidaysError}</p>}
            <div className="entry-list">
              {settings.holidays.map((h) => (
                <div className="entry-row entry-row-stack" key={h.id}>
                  <div className="entry-row-top">
                    <input
                      type="date"
                      value={h.date}
                      onChange={(e) => updateHoliday(h.id, { date: e.target.value })}
                    />
                    <span className={h.date ? 'entry-date' : 'entry-date is-empty'}>
                      {h.date ? formatDateForDisplay(h.date) : '—'}
                    </span>
                    <button aria-label="Видалити" className="icon-btn" onClick={() => removeHoliday(h.id)}>
                      ✕
                    </button>
                  </div>
                  <input
                    type="text"
                    className="entry-name"
                    placeholder="Назва свята"
                    value={h.name}
                    onChange={(e) => updateHoliday(h.id, { name: e.target.value })}
                  />
                </div>
              ))}
            </div>
            <button className="btn-secondary btn-block" onClick={addHolidayManual}>
              + Додати святковий день
            </button>
          </section>

          <section className="sidebar-block">
            <div className="sidebar-block-header">
              <h3>Перенесення вихідних днів</h3>
            </div>
            <div className="entry-list">
              {settings.dayTransfers.map((t) => (
                <div className="entry-row" key={t.id}>
                  <select value={t.type} onChange={(e) => updateTransfer(t.id, { type: e.target.value as DayTransfer['type'] })}>
                    <option value="toWorking">Зробити робочим</option>
                    <option value="toDayOff">Зробити вихідним</option>
                  </select>
                  <input
                    type="date"
                    value={t.date}
                    onChange={(e) => updateTransfer(t.id, { date: e.target.value })}
                  />
                  <button aria-label="Видалити" className="icon-btn" onClick={() => removeTransfer(t.id)}>
                    ✕
                  </button>
                </div>
              ))}
            </div>
            <div className="btn-row">
              <button className="btn-secondary" onClick={() => addTransfer('toWorking')}>
                + Робочий
              </button>
              <button className="btn-secondary" onClick={() => addTransfer('toDayOff')}>
                + Вихідний
              </button>
            </div>
          </section>

          <section className="sidebar-block">
            <div className="sidebar-block-header">
              <h3>Канікули</h3>
            </div>
            <div className="entry-list">
              {settings.vacations.map((v) => (
                <div className="entry-row" key={v.id}>
                  <input type="date" value={v.start} onChange={(e) => updateVacation(v.id, { start: e.target.value })} />
                  <span className="entry-dash">—</span>
                  <input type="date" value={v.end} onChange={(e) => updateVacation(v.id, { end: e.target.value })} />
                  <button aria-label="Видалити" className="icon-btn" onClick={() => removeVacation(v.id)}>
                    ✕
                  </button>
                </div>
              ))}
            </div>
            <button className="btn-secondary btn-block" onClick={addVacation}>
              + Додати канікули
            </button>
          </section>
        </aside>

        <main className="main-panel">
          <section className="card">
            <h3 className="section-label">Вибір семестру</h3>
            <div className="btn-row">
              <button className="btn-choice" onClick={applySemesterOne}>
                I семестр
              </button>
              <button className="btn-choice" onClick={applySemesterTwo}>
                II семестр
              </button>
            </div>

            <p className="section-sublabel">Або виберіть дату вручну</p>
            <div className="date-range-row">
              <label>
                Початкова дата
                <input
                  type="date"
                  value={settings.rangeStart}
                  onChange={(e) => updateSettings({ rangeStart: e.target.value })}
                />
              </label>
              <label>
                Кінцева дата
                <input
                  type="date"
                  value={settings.rangeEnd}
                  onChange={(e) => updateSettings({ rangeEnd: e.target.value })}
                />
              </label>
            </div>
          </section>

          <section className="card">
            <h3 className="section-label">Вибір днів тижня</h3>
            <div className="weekday-toggle-row">
              {WEEKDAY_BUTTON_LABELS.map((label, idx) => (
                <button
                  key={idx}
                  className={settings.weekdays[idx] > 0 ? 'weekday-btn active' : 'weekday-btn'}
                  onClick={() => toggleWeekday(idx)}
                  title={WEEKDAY_LABELS[idx]}
                >
                  {label}
                </button>
              ))}
            </div>

            <p className="section-sublabel">Кількість уроків на день</p>
            <div className="weekday-count-row">
              {WEEKDAY_BUTTON_LABELS.map((_, idx) => (
                <input
                  key={idx}
                  type="number"
                  min={0}
                  disabled={settings.weekdays[idx] === 0}
                  value={settings.weekdays[idx] ?? 0}
                  onChange={(e) => setLessonsPerDay(idx, Math.max(0, Number(e.target.value)))}
                />
              ))}
            </div>
            {selectedWeekdaysCount === 0 && (
              <p className="hint">Обери хоча б один день тижня вище.</p>
            )}
          </section>

          <section className="card">
            <label className="switch-row">
              <input
                type="checkbox"
                checked={settings.adaptiveWeekNumbering}
                onChange={(e) => updateSettings({ adaptiveWeekNumbering: e.target.checked })}
              />
              <span>Адаптивна система нумерації тижнів</span>
            </label>
            <p className="hint">
              Номер уроку матиме вигляд "тиждень.урок" (напр. 3.2), а тижні без жодного уроку
              (повністю в канікулах) не отримують номера — нумерація не має розривів.
            </p>

            <div className="starting-number-row">
              <span>Початковий порядковий номер уроку</span>
              <input
                type="number"
                min={1}
                value={settings.startingLessonNumber}
                onChange={(e) => updateSettings({ startingLessonNumber: Math.max(1, Number(e.target.value)) })}
                disabled={settings.adaptiveWeekNumbering}
              />
            </div>

            <div className="btn-row action-row">
              <button className="btn-primary" onClick={handleGenerate}>
                Почати
              </button>
              <button className="btn-secondary" onClick={handleReset}>
                Скинути
              </button>
            </div>
          </section>

          {lessons.length > 0 && (
            <section className="card">
              <div className="results-header">
                <h3 className="section-label">Результат</h3>
                <span className="results-count">{lessons.length} уроків</span>
              </div>
              <table className="results-table">
                <thead>
                  <tr>
                    <th>№</th>
                    <th>Дата</th>
                    <th>Д/Т</th>
                  </tr>
                </thead>
                <tbody>
                  {lessons.map((lesson, i) => (
                    <tr key={i}>
                      <td className="num-cell">{lesson.numberLabel}</td>
                      <td>{formatDateForDisplay(lesson.date)}</td>
                      <td className="dow-cell">{lesson.weekdayShort}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button className="btn-primary btn-block" onClick={handleExport}>
                Завантажити як XLSX
              </button>
            </section>
          )}
        </main>
      </div>
    </div>
  )
}

export default App

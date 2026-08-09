// Одноразовий скрипт підготовки шаблонів КТП для docxtemplater.
// Читає КТП_бланк_універсальний.docx і створює два шаблони:
//   public/ktp-sem1.docx — лише I семестр
//   public/ktp-sem2.docx — лише II семестр
// У кожному: шапкові теги {yearStart}, {yearEnd}, {school}, {subject}, {grade}, {teacher}
// та таблиця з одним зразковим рядком: {#rows}{num} {date} {hours} {/rows}.

import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import PizZip from 'pizzip'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const source = join(root, 'КТП_бланк_універсальний.docx')
const outDir = join(root, 'public')

if (!existsSync(source)) {
  console.error('Джерело не знайдено:', source)
  process.exit(1)
}

const zip = new PizZip(readFileSync(source))
const xml = zip.file('word/document.xml').asText()

// ---------- 1. Шапкові заміни (усі тексти в одному <w:t>, точні підрядки) ----------
function headerReplacements(sem) {
  const month = sem === 'sem1' ? 'вересень' : 'січень'
  const year = sem === 'sem1' ? '{yearStart}' : '{yearEnd}'
  return [
    ['на 20___ / 20___ навчальний рік', 'на {yearStart} / {yearEnd} навчальний рік. {semester}'],
    ['Заклад освіти: ____________________________________________________________', 'Заклад освіти: {school}'],
    ['Предмет (інтегрований курс): _______________________________________________________', 'Предмет (інтегрований курс): {subject}'],
    ['Клас(и): _______________________________________________________', 'Клас(и): {grade}'],
    ['Вчитель (ПІБ): _______________________________________________________', 'Вчитель (ПІБ): {teacher}'],
    ['Кількість годин на тиждень / на рік: _____________________________________________', 'Кількість годин на тиждень: {hoursPerWeek} годин, на рік: {hoursPerYear} годин.'],
    ['Директор ________________________________ (назва закладу освіти)', 'Директор {school}'],
    ['Вчитель: _______________________ /____________________/', `Вчитель: _______________________ /{teacher}`],
    ['«___» _____________ 20___ р.', `«___» ${month} ${year} р.`],
  ]
}

// ---------- 2. Виділення двох таблиць ----------
function findTable(xml, startFrom) {
  const start = xml.indexOf('<w:tbl>', startFrom)
  if (start === -1) throw new Error('Таблицю не знайдено')
  const end = xml.indexOf('</w:tbl>', start) + '</w:tbl>'.length
  return { start, end, body: xml.slice(start, end) }
}

const tbl1 = findTable(xml, 0)
const tbl2 = findTable(xml, tbl1.end)

// ---------- 3. Обрізка таблиці: лишити заголовок семестру + шапку колонок + один зразковий рядок ----------
function prepareTable(table) {
  let body = table.body

  const headerMark = '<w:tblHeader/>'
  const headerPos = body.indexOf(headerMark)
  if (headerPos === -1) throw new Error('Шапку колонок не знайдено')

  // Кінець шапки колонок = перший </w:tr> після tblHeader
  const headerEnd = body.indexOf('</w:tr>', headerPos) + '</w:tr>'.length

  // Перший порожній рядок після шапки — зразковий
  const sampleStart = body.indexOf('<w:tr ', headerEnd)
  if (sampleStart === -1) throw new Error('Зразковий рядок не знайдено')
  const sampleEnd = body.indexOf('</w:tr>', sampleStart) + '</w:tr>'.length
  let sample = body.slice(sampleStart, sampleEnd)

  // Заміна вмісту клітинок зразка (кожна клітинка має один <w:t xml:space="preserve"> </w:t>)
  // Заміни виконуємо з кінця в початок, щоб зсув позицій не ламав наступні
  const cellText = '<w:t xml:space="preserve"> </w:t>'
  const slots = []
  let pos = 0
  while (sample.includes(cellText, pos)) {
    const i = sample.indexOf(cellText, pos)
    slots.push(i)
    pos = i + cellText.length
  }
  if (slots.length < 5) throw new Error(`Очікувано 5 клітинок у зразку, знайдено ${slots.length}`)

  const replacements = [
    [4, '{/rows}'],
    [3, '{hours}'],
    [1, '{date}'],
    [0, '{#rows}{num}'],
  ]
  for (const [slotIdx, text] of replacements) {
    const i = slots[slotIdx]
    sample = sample.slice(0, i) + `<w:t>${text}</w:t>` + sample.slice(i + cellText.length)
  }

  // Вміст клітинок зразкового рядка — по центру
  sample = sample.replace(
    /<w:p w14:paraId="[^"]+" w14:textId="[^"]+" w:rsidR="[^"]+" w:rsidRDefault="[^"]+">/g,
    (m) => m + '<w:pPr><w:jc w:val="center"/></w:pPr>',
  )

  return body.slice(0, headerEnd) + sample + '</w:tbl>'
}

// ---------- 4. Збірка документів ----------
function build(keepTable) {
  const prefix = xml.slice(0, tbl1.start)
  const middle = keepTable === 'tbl1'
    ? prepareTable(tbl1)
    : prepareTable(tbl2)
  const suffix = xml.slice(tbl2.end)

  let out = prefix + middle + suffix
  const sem = keepTable === 'tbl1' ? 'sem1' : 'sem2'
  for (const [from, to] of headerReplacements(sem)) {
    if (!out.includes(from)) throw new Error('Не знайдено текст для заміни: ' + from.slice(0, 40))
    out = out.split(from).join(to)
  }
  return out
}

for (const [name, table] of [['ktp-sem1.docx', 'tbl1'], ['ktp-sem2.docx', 'tbl2']]) {
  const outXml = build(table)
  const outZip = new PizZip()
  for (const entry of Object.values(zip.files)) {
    if (entry.dir) continue
    outZip.file(entry.name, entry.asText())
  }
  outZip.file('word/document.xml', outXml)
  if (!existsSync(outDir)) mkdirSync(outDir, { recursive: true })
  writeFileSync(join(outDir, name), outZip.generate({ type: 'nodebuffer' }))
  console.log('Створено', join(outDir, name), '—', outZip.generate({ type: 'nodebuffer' }).length, 'байт')
}

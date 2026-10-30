---
name: md-justify
description: Скрипты подготовки и сборки перевода — извлечение текста из epub/pdf (extract_sources.py), выравнивание EN/UK/RU по абзацам (split_align.py), выключка строк до 85 символов (justify.py) и проверка формата (check_format.py).
---

# md-justify: скрипты пайплайна

Все скрипты — Python 3, стандартная библиотека (extract_sources.py для UA-PDF
вызывает системный `pdftotext`). Запускать из корня репозитория.

## extract_sources.py

```bash
python3 .claude/skills/md-justify/scripts/extract_sources.py [--root .]
```

Читает исходные epub/pdf (не изменяя их) и пишет `sources/EN.md`,
`sources/UK.md`, `sources/RU.md`: заголовок `# [<part>] <title>` на каждую
часть (prologue, ch1…ch6, epilogue), абзац = одна строка, между абзацами
пустая строка, эпиграфы с префиксом `> `. Для UA-PDF: склейка переносов,
удаление колонтитулов/номеров страниц, пропуск страниц с картами/фото,
восстановление абзацев (буквицы, блочные цитаты, разрывы страниц).

## split_align.py

```bash
python3 .claude/skills/md-justify/scripts/split_align.py --part prologue --model fable
```

Извлекает часть из sources/*.md, выравнивает EN↔UK↔RU (DP по длинам,
Gale–Church), пишет `work/<part>/<model>/segments.md` (таблица
`ID | EN | UK | RU`, ID = P001…, опора — абзацы EN) и `align_report.md` +
stdout: попарные расхождения EN/UK, EN/RU, UK/RU с точным указанием
абзацев, где они начинаются.

## justify.py

```bash
python3 .claude/skills/md-justify/scripts/justify.py clean.md -o out_BY.md [--width 85]
```

Вход — «чистый» файл: абзац = одна строка, абзацы через пустую строку,
заголовки `#`. Выход: строки ≤ 85 символов Unicode; жадное заполнение;
все строки абзаца, кроме последней, растянуты до ровно 85 — дополнительные
пробелы добавляются в промежутки начиная с середины строки, расходясь к
краям; последняя строка и строки из одного слова не растягиваются; слово
длиннее 85 остаётся на своей строке; без хвостовых пробелов; заголовки не
выравниваются.

## check_format.py

```bash
python3 .claude/skills/md-justify/scripts/check_format.py out_BY.md --part 0
```

Проверяет все правила justify + (с `--part N` или `--en FILE`) равенство
числа абзацев BY и EN. Код выхода 0 = OK, 1 = нарушения (список в stdout
и stderr).
